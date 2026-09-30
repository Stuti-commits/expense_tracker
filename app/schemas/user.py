from pydantic import BaseModel


class UserOut(BaseModel):
    id: str
    email: str | None
    display_name: str | None
    tier_thresholds: dict

    model_config = {"from_attributes": True}


class TierThresholdsUpdate(BaseModel):
    primary: float
    secondary: float
