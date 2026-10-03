import hashlib

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, CurrentUser
from app.db.database import get_db
from app.models.statement import Statement, StatementStatus
from app.models.transaction import Transaction, TransactionDirection
from app.services.pdf_decrypt import decrypt_pdf_or_422
from app.services.pdf_text_extract import extract_text_from_pdf
from app.services.parsers.registry import get_parser
from app.services.merchant_normalize import normalize_merchant
from app.services.tx_hash import compute_tx_hash

router = APIRouter(prefix="/statements", tags=["statements"])


@router.post("/upload")
async def upload_statement(
    bank_name: str = Form(...),
    password: str = Form(...),
    debug_raw_text: bool = Form(False),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Uploads an encrypted bank statement PDF, decrypts it in memory, extracts
    text, parses it into transaction lines, normalizes merchant names, and
    inserts new transactions into the DB -- skipping any that already exist
    (by tx_hash) or any file already uploaded (by file_hash).

    category/tier on inserted rows are placeholders (`other` / `not_applicable`)
    for now -- classification logic is the next phase. This phase's job is
    correct, deduped insertion; classification will UPDATE these rows later
    rather than needing a second insert path.

    debug_raw_text=true: decrypts and extracts text ONLY -- no database
    writes at all, safe to call repeatedly on the same file.
    """
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file uploaded.")

    # --- Debug mode: no DB interaction, same as before. ---
    if debug_raw_text:
        decrypted_bytes = decrypt_pdf_or_422(file_bytes, password)
        raw_text = extract_text_from_pdf(decrypted_bytes)
        return {
            "mode": "debug_raw_text",
            "note": "No database row was created for this preview.",
            "raw_text": raw_text,
        }

    # --- File-hash dedup: same user, same exact file already uploaded. ---
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    existing_statement = (
        db.query(Statement)
        .filter(Statement.user_id == user.uid, Statement.file_hash == file_hash)
        .first()
    )
    if existing_statement is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This exact file was already uploaded (statement_id={existing_statement.id}, "
            f"status={existing_statement.status.value}).",
        )

    statement = Statement(
        user_id=user.uid,
        bank_name=bank_name,
        file_hash=file_hash,
        status=StatementStatus.processing,
    )
    db.add(statement)
    db.commit()
    db.refresh(statement)

    try:
        decrypted_bytes = decrypt_pdf_or_422(file_bytes, password)
        raw_text = extract_text_from_pdf(decrypted_bytes)

        try:
            parser_fn = get_parser(bank_name)
        except ValueError as e:
            statement.status = StatementStatus.failed
            statement.failure_reason = str(e)
            db.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        parsed_lines = parser_fn(raw_text)

        if not parsed_lines:
            statement.status = StatementStatus.failed
            statement.failure_reason = (
                "Parser matched 0 transaction lines. Re-check the statement's "
                "text layout with debug_raw_text=true."
            )
            db.commit()
            return {
                "statement_id": str(statement.id),
                "status": "failed",
                "reason": statement.failure_reason,
                "raw_text_preview": raw_text[:1000],
            }

        # --- Transaction-hash dedup + insert ---
        inserted = []
        skipped_duplicates = []

        for line in parsed_lines:
            merchant_normalized = normalize_merchant(bank_name, line.narration_raw)
            tx_hash = compute_tx_hash(
                user_id=user.uid,
                tx_date=line.date,
                amount=line.amount,
                direction=line.direction.value,
                merchant_raw=line.narration_raw,
            )

            existing_tx = db.query(Transaction).filter(Transaction.tx_hash == tx_hash).first()
            if existing_tx is not None:
                skipped_duplicates.append(
                    {
                        "date": line.date.isoformat(),
                        "amount": str(line.amount),
                        "merchant_raw": line.narration_raw,
                        "reason": f"Duplicate of existing transaction {existing_tx.id}",
                    }
                )
                continue

            tx = Transaction(
                statement_id=statement.id,
                user_id=user.uid,
                date=line.date,
                amount=line.amount,
                direction=TransactionDirection(line.direction.value),
                merchant_raw=line.narration_raw,
                merchant_normalized=merchant_normalized,
                # Placeholders -- classification phase will update these.
                # category defaults to "other", tier to "not_applicable" per the model.
                is_manual_override=False,
                tx_hash=tx_hash,
            )
            db.add(tx)
            inserted.append(tx)

        db.commit()
        for tx in inserted:
            db.refresh(tx)

        statement.status = StatementStatus.parsed
        db.commit()

        return {
            "statement_id": str(statement.id),
            "status": "parsed",
            "inserted_count": len(inserted),
            "skipped_duplicate_count": len(skipped_duplicates),
            "transactions": [
                {
                    "id": str(tx.id),
                    "date": tx.date.isoformat(),
                    "merchant_raw": tx.merchant_raw,
                    "merchant_normalized": tx.merchant_normalized,
                    "amount": str(tx.amount),
                    "direction": tx.direction.value,
                    "category": tx.category.value,
                    "tier": tx.tier.value,
                }
                for tx in inserted
            ],
            "skipped_duplicates": skipped_duplicates,
        }

    except HTTPException:
        statement.status = StatementStatus.failed
        statement.failure_reason = "See HTTP error detail."
        db.commit()
        raise
    except Exception as e:
        db.rollback()
        statement.status = StatementStatus.failed
        statement.failure_reason = f"Unexpected error: {e}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while processing statement.",
        )
