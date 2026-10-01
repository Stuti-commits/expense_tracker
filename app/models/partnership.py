import uuid
import enum

from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class PartnershipStatus(str, enum.Enum):
    pending = "pending"     # invite sent, not yet accepted
    active = "active"       # partner accepted, goal tracking is live
    completed = "completed" # goal reached or end_date passed
    declined = "declined"   # partner declined the invite


class Partnership(Base):
    """
    Links user_a (creator) and user_b (invited partner) to a single shared Goal.
    user_b_id is nullable because at invite-creation time, the partner hasn't
    accepted (or even necessarily has an account) yet — it's filled in once
    they accept via invite_token.

    One partnership per goal: goal_id is unique, so a goal can't accidentally
    be attached to two different partnerships.
    """

    __tablename__ = "partnerships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_a_id = Column(String, nullable=False, index=True)  # Firebase UID, creator
    user_b_id = Column(String, nullable=True, index=True)   # Firebase UID, filled on accept

    goal_id = Column(
        UUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    status = Column(
        Enum(PartnershipStatus, name="partnership_status"),
        nullable=False,
        default=PartnershipStatus.pending,
    )

    invite_token = Column(String, nullable=False, unique=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ends_at = Column(DateTime(timezone=True), nullable=True)
