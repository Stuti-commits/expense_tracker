from pydantic import BaseModel
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.models.transaction import TransactionCategory, TransactionTier, TransactionDirection


class TransactionOut(BaseModel):
    id: UUID
    date: date
    amount: Decimal
    direction: TransactionDirection
    merchant_raw: str
    merchant_normalized: str
    category: TransactionCategory
    tier: TransactionTier
    is_manual_override: bool

    model_config = {"from_attributes": True}


class TransactionCorrectionIn(BaseModel):
    category: TransactionCategory
    # Optional: if omitted, tier is auto-computed from this transaction's own
    # amount/direction via the user's threshold settings -- most corrections
    # should NOT need to set this manually, only pass it if you specifically
    # want this merchant pinned to a tier regardless of amount.
    tier: TransactionTier | None = None
    # If true (default), every OTHER existing transaction from this same
    # merchant (for this user) is also reclassified now, not just this one.
    apply_to_existing: bool = True


class ReclassifyResult(BaseModel):
    reclassified_count: int
