from pydantic import BaseModel
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.models.goal import GoalType, GoalPeriod, GoalStatus
from app.models.partnership import PartnershipStatus


class GoalCreateIn(BaseModel):
    target_amount: Decimal
    period: GoalPeriod
    start_date: date
    end_date: date


class GoalOut(BaseModel):
    id: UUID
    type: GoalType
    period: GoalPeriod
    status: GoalStatus
    target_amount: Decimal
    current_amount: Decimal
    start_date: date
    end_date: date
    created_at: datetime

    model_config = {"from_attributes": True}


class ContributionIn(BaseModel):
    amount: Decimal


class PartnershipOut(BaseModel):
    id: UUID
    goal_id: UUID
    user_a_id: str
    user_b_id: str | None
    status: PartnershipStatus
    invite_token: str
    created_at: datetime
    ends_at: datetime | None

    model_config = {"from_attributes": True}


class PartnershipGoalCreateOut(BaseModel):
    goal: GoalOut
    partnership: PartnershipOut


class PartnershipTokenIn(BaseModel):
    invite_token: str
