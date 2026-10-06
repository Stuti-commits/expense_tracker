from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.deps import get_current_user, CurrentUser
from app.db.database import get_db
from app.models.user import User
from app.models.transaction import Transaction, TransactionDirection, TransactionTier
from app.models.merchant_override import MerchantOverride
from app.schemas.transaction import TransactionOut, TransactionCorrectionIn, ReclassifyResult
from app.services.classification import classify_transaction, compute_tier_from_amount

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _get_user_row(db: Session, uid: str) -> User:
    user_row = db.query(User).filter(User.id == uid).first()
    if user_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Call POST /users/sync first.",
        )
    return user_row


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists all of the current user's transactions, most recent first."""
    return (
        db.query(Transaction)
        .filter(Transaction.user_id == user.uid)
        .order_by(Transaction.date.desc())
        .all()
    )


@router.put("/{transaction_id}/classify", response_model=TransactionOut)
def correct_transaction_classification(
    transaction_id: UUID,
    payload: TransactionCorrectionIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lets a user correct one transaction's category. This does two things:

    1. Updates the transaction itself (category + recomputed tier,
       is_manual_override=True so it's never silently overwritten by a
       future bulk reclassify unless the user corrects it again).
    2. Upserts a merchant_overrides row so future uploads from this same
       merchant are classified correctly automatically -- this is the
       "apply this to all future transactions from this merchant" behavior,
       defaulted to on.

    If apply_to_existing=true (default), every OTHER existing transaction
    from this same merchant is ALSO reclassified right now -- each one
    recomputed individually via its own amount/direction, not copy-pasted
    from this transaction, so the credit-tier invariant still holds even
    if this merchant has both debits and credits in your history.
    """
    tx = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.user_id == user.uid)
        .first()
    )
    if tx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found (or doesn't belong to you).",
        )

    user_row = _get_user_row(db, user.uid)

    # --- Resolve this transaction's own tier ---
    if tx.direction == TransactionDirection.credit:
        tx.tier = TransactionTier.not_applicable
    elif payload.tier is not None:
        tx.tier = payload.tier
    else:
        tx.tier = compute_tier_from_amount(tx.amount, user_row.tier_thresholds or {})

    tx.category = payload.category
    tx.is_manual_override = True

    # --- Upsert merchant_overrides ---
    # The override's stored tier is: what the user explicitly passed, OR
    # this transaction's own resolved tier as a sensible default. Credits
    # never get stored as a spend tier here either, for the same reason.
    override_tier = (
        TransactionTier.not_applicable
        if tx.direction == TransactionDirection.credit
        else (payload.tier if payload.tier is not None else tx.tier)
    )

    existing_override = (
        db.query(MerchantOverride)
        .filter(
            MerchantOverride.user_id == user.uid,
            MerchantOverride.merchant_normalized == tx.merchant_normalized,
        )
        .first()
    )
    if existing_override is not None:
        existing_override.category = payload.category
        existing_override.tier = override_tier
    else:
        db.add(
            MerchantOverride(
                user_id=user.uid,
                merchant_normalized=tx.merchant_normalized,
                category=payload.category,
                tier=override_tier,
            )
        )

    db.commit()
    db.refresh(tx)

    # --- Optionally reclassify every other existing transaction from this merchant ---
    if payload.apply_to_existing:
        other_txs = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == user.uid,
                Transaction.merchant_normalized == tx.merchant_normalized,
                Transaction.id != tx.id,
            )
            .all()
        )
        for other in other_txs:
            category, tier = classify_transaction(
                db, user_row, other.merchant_normalized, other.amount, other.direction
            )
            other.category = category
            other.tier = tier
            # Not marking is_manual_override=True here -- these weren't
            # individually reviewed, they inherited the merchant rule.
        db.commit()

    return tx


@router.post("/reclassify-unclassified", response_model=ReclassifyResult)
def reclassify_unclassified(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Re-runs classification on every transaction that has NOT been manually
    corrected (is_manual_override=False) -- including ones currently sitting
    at the "other" / "not_applicable" placeholder values from before this
    phase existed.

    Safe to call any time, not just once: e.g. after adding a merchant
    override, or after a future update to the keyword rules, run this again
    to apply the improvement retroactively.

    Transactions with is_manual_override=True are intentionally skipped --
    a manual correction should not be silently undone by a bulk run.
    """
    user_row = _get_user_row(db, user.uid)

    unclassified = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.uid, Transaction.is_manual_override == False)  # noqa: E712
        .all()
    )

    for tx in unclassified:
        category, tier = classify_transaction(
            db, user_row, tx.merchant_normalized, tx.amount, tx.direction
        )
        tx.category = category
        tx.tier = tier

    db.commit()

    return ReclassifyResult(reclassified_count=len(unclassified))
