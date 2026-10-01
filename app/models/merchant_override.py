import uuid

from sqlalchemy import Column, String, Enum, DateTime, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base
from app.models.transaction import TransactionCategory, TransactionTier


class MerchantOverride(Base):
    """
    Per-user corrections: "transactions from this merchant should always be
    classified this way." This is checked FIRST in the classification pipeline,
    before category keyword rules or amount-threshold fallback.

    Unique on (user_id, merchant_normalized) — one rule per merchant per user.
    A new correction for the same merchant should UPDATE this row, not insert
    a second one.
    """

    __tablename__ = "merchant_overrides"
    __table_args__ = (
        UniqueConstraint("user_id", "merchant_normalized", name="uq_override_user_merchant"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(String, nullable=False, index=True)  # Firebase UID
    merchant_normalized = Column(String, nullable=False)

    category = Column(Enum(TransactionCategory, name="transaction_category"), nullable=False)
    tier = Column(Enum(TransactionTier, name="transaction_tier"), nullable=False)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
