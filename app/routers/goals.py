import secrets
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, CurrentUser
from app.db.database import get_db
from app.models.goal import Goal, GoalType, GoalStatus
from app.models.partnership import Partnership, PartnershipStatus
from app.schemas.goal import (
    GoalCreateIn,
    GoalOut,
    ContributionIn,
    PartnershipOut,
    PartnershipGoalCreateOut,
    PartnershipTokenIn,
)

router = APIRouter(prefix="/goals", tags=["goals"])


# --- Lazy expiration -------------------------------------------------------
# No background scheduler in this project -- instead, every time a goal is
# read, we check whether its end_date has passed and flip it to `completed`
# right then if so. This means a goal won't expire at the exact stroke of
# midnight, only the next time someone looks at it -- an acceptable
# tradeoff here, but worth knowing it's a deliberate simplification, not
# an oversight, if this ever comes up.
def _sync_goal_expiry(db: Session, goal: Goal, partnership: Partnership | None) -> None:
    if goal.status == GoalStatus.active and goal.end_date < date.today():
        goal.status = (
            GoalStatus.completed if goal.current_amount >= goal.target_amount else GoalStatus.missed
        )
        if partnership is not None and partnership.status == PartnershipStatus.active:
            partnership.status = PartnershipStatus.completed
        db.commit()


def _maybe_complete_on_target_reached(db: Session, goal: Goal, partnership: Partnership | None) -> None:
    if goal.status == GoalStatus.active and goal.current_amount >= goal.target_amount:
        goal.status = GoalStatus.completed
        if partnership is not None and partnership.status == PartnershipStatus.active:
            partnership.status = PartnershipStatus.completed
        db.commit()


def _get_partnership_for_goal(db: Session, goal_id: UUID) -> Partnership | None:
    return db.query(Partnership).filter(Partnership.goal_id == goal_id).first()


def _get_goal_with_auth(db: Session, goal_id: UUID, user_uid: str) -> tuple[Goal, Partnership | None]:
    """
    Fetches a goal and enforces access: the goal's own creator always has
    access; for a partnership goal, the accepted partner (user_b) also has
    access once the partnership is active. A pending invite's user_b (not
    yet accepted) has NO access until they accept.
    """
    goal = db.query(Goal).filter(Goal.id == goal_id).first()
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")

    partnership = _get_partnership_for_goal(db, goal.id) if goal.type == GoalType.partnership else None

    authorized = goal.user_id == user_uid
    if partnership is not None:
        authorized = authorized or (
            partnership.user_b_id == user_uid and partnership.status == PartnershipStatus.active
        )

    if not authorized:
        # 404, not 403 -- don't reveal that a goal with this id exists to
        # someone who isn't part of it.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")

    _sync_goal_expiry(db, goal, partnership)
    return goal, partnership


# --- Personal goals ---------------------------------------------------------

@router.post("", response_model=GoalOut)
def create_personal_goal(
    payload: GoalCreateIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = Goal(
        user_id=user.uid,
        type=GoalType.personal,
        period=payload.period,
        status=GoalStatus.active,
        target_amount=payload.target_amount,
        current_amount=0,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.get("", response_model=list[GoalOut])
def list_my_goals(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns every goal the user can see: their own personal goals, their own
    partnership goals (as creator, any status), and partnership goals where
    they're the ACTIVE accepted partner. A pending invite they haven't
    accepted yet does not show up here -- use GET /goals/partnership/pending
    for that.
    """
    own_goals = db.query(Goal).filter(Goal.user_id == user.uid).all()

    partner_goal_ids = [
        p.goal_id
        for p in db.query(Partnership)
        .filter(Partnership.user_b_id == user.uid, Partnership.status == PartnershipStatus.active)
        .all()
    ]
    partner_goals = db.query(Goal).filter(Goal.id.in_(partner_goal_ids)).all() if partner_goal_ids else []

    all_goals = own_goals + partner_goals

    for g in all_goals:
        partnership = _get_partnership_for_goal(db, g.id) if g.type == GoalType.partnership else None
        _sync_goal_expiry(db, g, partnership)

    return all_goals


@router.get("/{goal_id}", response_model=GoalOut)
def get_goal(
    goal_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal, _ = _get_goal_with_auth(db, goal_id, user.uid)
    return goal


@router.patch("/{goal_id}/contribute", response_model=GoalOut)
def contribute_to_goal(
    goal_id: UUID,
    payload: ContributionIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually records a contribution toward a goal. This is NOT derived from
    parsed bank transactions -- there's no reliable way to tell from a
    passbook PDF which debit was "money set aside for this goal" vs. an
    ordinary expense, so the user (or their accepted partner) logs it
    directly here.
    """
    if payload.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contribution amount must be positive.")

    goal, partnership = _get_goal_with_auth(db, goal_id, user.uid)

    if goal.status != GoalStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This goal is {goal.status.value}, not active -- contributions are no longer accepted.",
        )

    goal.current_amount = goal.current_amount + payload.amount
    db.commit()
    db.refresh(goal)

    _maybe_complete_on_target_reached(db, goal, partnership)
    db.refresh(goal)
    return goal


# --- Partnership goals -------------------------------------------------------

@router.post("/partnership", response_model=PartnershipGoalCreateOut)
def create_partnership_goal(
    payload: GoalCreateIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates a partnership goal and a pending invite. The goal itself starts
    `active`, but the PARTNERSHIP starts `pending` -- the menu feature this
    unlocks for both users should only show once the partnership itself
    becomes `active` (i.e. after the invite is accepted), not just because
    the goal exists.
    """
    goal = Goal(
        user_id=user.uid,
        type=GoalType.partnership,
        period=payload.period,
        status=GoalStatus.active,
        target_amount=payload.target_amount,
        current_amount=0,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    db.add(goal)
    db.flush()  # assigns goal.id without committing yet

    invite_token = secrets.token_urlsafe(24)
    ends_at = datetime.combine(payload.end_date, datetime.min.time(), tzinfo=timezone.utc)

    partnership = Partnership(
        user_a_id=user.uid,
        user_b_id=None,
        goal_id=goal.id,
        status=PartnershipStatus.pending,
        invite_token=invite_token,
        ends_at=ends_at,
    )
    db.add(partnership)
    db.commit()
    db.refresh(goal)
    db.refresh(partnership)

    return PartnershipGoalCreateOut(goal=goal, partnership=partnership)


@router.get("/partnership/pending", response_model=list[PartnershipOut])
def list_pending_invites_sent_by_me(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Partnership invites YOU created that haven't been accepted/declined yet."""
    return (
        db.query(Partnership)
        .filter(Partnership.user_a_id == user.uid, Partnership.status == PartnershipStatus.pending)
        .all()
    )


@router.post("/partnership/accept", response_model=PartnershipOut)
def accept_partnership_invite(
    payload: PartnershipTokenIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    The invited partner calls this with the invite_token to accept. Per the
    earlier design decision: the partner MUST have their own Firebase
    account and be authenticated -- there's no accountless path.
    """
    partnership = db.query(Partnership).filter(Partnership.invite_token == payload.invite_token).first()
    if partnership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found.")

    if partnership.status != PartnershipStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This invite is {partnership.status.value}, not pending.",
        )

    if partnership.user_a_id == user.uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You can't accept your own invite.")

    goal = db.query(Goal).filter(Goal.id == partnership.goal_id).first()
    if goal is not None and goal.end_date < date.today():
        partnership.status = PartnershipStatus.declined
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This invite has expired.")

    partnership.user_b_id = user.uid
    partnership.status = PartnershipStatus.active
    db.commit()
    db.refresh(partnership)
    return partnership


@router.post("/partnership/decline", response_model=PartnershipOut)
def decline_partnership_invite(
    payload: PartnershipTokenIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    partnership = db.query(Partnership).filter(Partnership.invite_token == payload.invite_token).first()
    if partnership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found.")

    if partnership.status != PartnershipStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This invite is {partnership.status.value}, not pending.",
        )

    partnership.status = PartnershipStatus.declined
    db.commit()
    db.refresh(partnership)
    return partnership
