import uuid
import enum

from sqlalchemy import Column, String, DateTime, Enum, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class StatementStatus(str, enum.Enum):
    processing = "processing"
    parsed = "parsed"
    failed = "failed"


class Statement(Base):
    """
    One row per uploaded bank statement PDF.

    file_hash + user_id are unique together — this is the first line of
    defense against a user re-uploading the same statement twice. It's
    scoped per-user (not global) because two different users could
    legitimately upload byte-identical files only in freak edge cases,
    and scoping to user_id avoids ever rejecting someone else's valid
    upload by coincidence.
    """

    __tablename__ = "statements"
    __table_args__ = (
        UniqueConstraint("user_id", "file_hash", name="uq_statement_user_filehash"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(String, nullable=False, index=True)  # Firebase UID
    bank_name = Column(String, nullable=False)  # e.g. "karnataka_bank" — matches a parser module name

    file_hash = Column(String, nullable=False)  # SHA-256 of the raw uploaded file
    status = Column(
        Enum(StatementStatus, name="statement_status"),
        nullable=False,
        default=StatementStatus.processing,
    )
    failure_reason = Column(String, nullable=True)  # set when status == failed, for debugging/support

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
