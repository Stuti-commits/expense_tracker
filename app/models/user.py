from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base


class User(Base):
    """
    NOTE: Firebase owns identity (email, password, login). This table does NOT
    duplicate that. It only stores app-specific data tied to a Firebase user,
    keyed by their Firebase UID.

    id is a string (Firebase UID), not an auto-increment int — every other
    table's user_id foreign key must also be String, not Integer.
    """

    __tablename__ = "users"

    id = Column(String, primary_key=True)  # Firebase UID
    email = Column(String, nullable=True)  # cached from Firebase token for convenience only
    display_name = Column(String, nullable=True)

    # e.g. {"primary": 10000, "secondary": 5000}
    # Used as the fallback tier-classification rule when no category/merchant match is found.
    tier_thresholds = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
