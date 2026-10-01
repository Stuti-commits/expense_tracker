import uuid
import enum

from sqlalchemy import Column, String, Numeric, Date, DateTime, Enum, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class GoalType(str, enum.Enum):
    personal = "personal"
    partnership = "partnership"


class GoalPeriod(str, enum.Enum):
    weekly = "weekly"
    monthly = "monthly"


class GoalStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    abandoned = "abandoned"


class Goal(Base):
    """
    Covers both personal savings/investment goals and partnership goals.
    A partnership goal is still just a Goal row — the `partnerships` table
    links two users to one goal rather than duplicating goal logic.
    """

    __tablename__ = "goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Firebase UID of the goal's owner/creator. For partnership goals, this is
    # whoever created the goal — the partner is linked via the `partnerships` table.
    user_id = Column(String, nullable=False, index=True)

    type = Column(Enum(GoalType, name="goal_type"), nullable=False)
    period = Column(Enum(GoalPeriod, name="goal_period"), nullable=False)
    status = Column(
        Enum(GoalStatus, name="goal_status"), nullable=False, default=GoalStatus.active
    )

    target_amount = Column(Numeric(12, 2), nullable=False)
    current_amount = Column(Numeric(12, 2), nullable=False, default=0)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
