import uuid
import enum

from sqlalchemy import (
    Column,
    String,
    Numeric,
    Date,
    Boolean,
    Enum,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class TransactionDirection(str, enum.Enum):
    debit = "debit"
    credit = "credit"


class TransactionCategory(str, enum.Enum):
    rent = "rent"
    emi = "emi"
    groceries = "groceries"
    utilities = "utilities"
    food_delivery = "food_delivery"
    shopping = "shopping"
    entertainment = "entertainment"
    transfer = "transfer"
    income = "income"
    other = "other"


class TransactionTier(str, enum.Enum):
    primary = "primary"
    secondary = "secondary"
    tertiary = "tertiary"
    # Income/transfers are excluded from tier ranking entirely rather than
    # forced into one of the three buckets — see note in classification logic.
    not_applicable = "not_applicable"


class Transaction(Base):
    """
    One parsed line item from a statement.

    tx_hash is the dedup key: hash of (statement_id, date, amount, direction,
    merchant_raw). Unique constraint on it means a re-parsed or overlapping
    statement can't silently double-insert the same transaction.

    is_manual_override tracks whether a human corrected the category/tier —
    this is what merchant_overrides consumes to improve future classification,
    and it's also what should be excluded if you ever retrain a real classifier
    vs. treating it as ground truth.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("tx_hash", name="uq_transaction_hash"),
        Index("ix_transactions_user_date", "user_id", "date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    statement_id = Column(
        UUID(as_uuid=True), ForeignKey("statements.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(String, nullable=False)  # Firebase UID — denormalized from statement for query speed

    date = Column(Date, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    direction = Column(Enum(TransactionDirection, name="transaction_direction"), nullable=False)

    merchant_raw = Column(String, nullable=False)        # exact narration string from the PDF
    merchant_normalized = Column(String, nullable=False, index=True)  # cleaned/matched merchant name

    category = Column(
        Enum(TransactionCategory, name="transaction_category"),
        nullable=False,
        default=TransactionCategory.other,
    )
    tier = Column(
        Enum(TransactionTier, name="transaction_tier"),
        nullable=False,
        default=TransactionTier.not_applicable,
    )

    is_manual_override = Column(Boolean, nullable=False, default=False)

    tx_hash = Column(String, nullable=False)
