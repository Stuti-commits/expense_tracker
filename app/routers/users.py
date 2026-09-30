from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, CurrentUser
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserOut, TierThresholdsUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/sync", response_model=UserOut)
def sync_current_user(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Call this once right after a user logs in on the client (Firebase handles
    the actual login). This creates the local `users` row on first sign-in,
    or just returns the existing one on subsequent calls.

    Firebase never tells your backend "a new user signed up" by itself —
    this endpoint is how your DB finds out a user exists.
    """
    db_user = db.query(User).filter(User.id == user.uid).first()
    if db_user is None:
        db_user = User(
            id=user.uid,
            email=user.email,
            tier_thresholds={"primary": 10000, "secondary": 5000},  # sensible defaults
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    return db_user


@router.get("/me", response_model=UserOut)
def get_me(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_user = db.query(User).filter(User.id == user.uid).first()
    if db_user is None:
        # Defensive: shouldn't happen if the client always calls /sync after login,
        # but don't 500 if it does — tell the caller what to do.
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Call POST /users/sync first.",
        )
    return db_user


@router.put("/me/tier-thresholds", response_model=UserOut)
def update_tier_thresholds(
    payload: TierThresholdsUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lets the user set their fallback classification thresholds
    (e.g. above 10k = primary, above 5k = secondary, rest = tertiary).
    This is only the FALLBACK rule — merchant overrides and category rules
    take priority over this during classification.
    """
    db_user = db.query(User).filter(User.id == user.uid).first()
    db_user.tier_thresholds = {
        "primary": payload.primary,
        "secondary": payload.secondary,
    }
    db.commit()
    db.refresh(db_user)
    return db_user
