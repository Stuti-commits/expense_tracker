import hashlib

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, CurrentUser
from app.db.database import get_db
from app.models.statement import Statement, StatementStatus
from app.services.pdf_decrypt import decrypt_pdf_or_422
from app.services.pdf_text_extract import extract_text_from_pdf
from app.services.parsers.registry import get_parser

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
    text, and (unless debug_raw_text=true) runs it through the bank's parser.

    debug_raw_text=true: decrypts and extracts text ONLY -- no database
    writes at all. Use this to preview a statement's text layout as many
    times as you want without it counting as a real upload or blocking a
    later real upload of the same file.

    This endpoint does NOT write to the `transactions` table. It returns
    parsed lines for inspection. Classification + DB insert happen in the
    next phase.
    """
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file uploaded.")

    # --- Debug mode: decrypt + extract only, NO database interaction at all. ---
    # This must happen BEFORE the dedup check / Statement row creation below,
    # so previewing a file never creates a row that could block a real upload
    # of that same file later.
    if debug_raw_text:
        decrypted_bytes = decrypt_pdf_or_422(file_bytes, password)
        raw_text = extract_text_from_pdf(decrypted_bytes)
        return {
            "mode": "debug_raw_text",
            "note": "No database row was created for this preview.",
            "raw_text": raw_text,
        }

    # --- Real processing attempt from here on: dedup check + Statement row apply. ---
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    existing = (
        db.query(Statement)
        .filter(Statement.user_id == user.uid, Statement.file_hash == file_hash)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This exact file was already uploaded (statement_id={existing.id}, "
            f"status={existing.status.value}).",
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

        statement.status = StatementStatus.parsed
        db.commit()

        return {
            "statement_id": str(statement.id),
            "status": "parsed",
            "transaction_count": len(parsed_lines),
            "transactions": [
                {
                    "date": line.date.isoformat(),
                    "narration_raw": line.narration_raw,
                    "amount": str(line.amount),
                    "direction": line.direction.value,
                }
                for line in parsed_lines
            ],
        }

    except HTTPException:
        statement.status = StatementStatus.failed
        statement.failure_reason = "See HTTP error detail."
        db.commit()
        raise
    except Exception as e:
        statement.status = StatementStatus.failed
        statement.failure_reason = f"Unexpected error: {e}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while processing statement.",
        )
