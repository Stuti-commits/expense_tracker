"""
Classification engine: turns (merchant_normalized, amount, direction) into
(category, tier) using 3-step priority logic.

    1. merchant_overrides lookup (user-specific correction) -- highest priority
    2. keyword-based category rules (generic, not user-specific)
    3. amount-threshold fallback (user's own tier_thresholds) -- tier only,
       category falls back to `other` if no keyword matched

INVARIANT THAT IS NEVER BROKEN, REGARDLESS OF WHAT STEP 1/2 SAY:
    direction == credit  =>  tier is ALWAYS not_applicable.
Income/incoming transfers are never ranked as primary/secondary/tertiary
spend, even if a merchant override exists that was set from a different
(debit) transaction with that merchant. This is enforced in one place
(here) so it can't be silently bypassed by a bad override row.
"""

import re
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.transaction import TransactionCategory, TransactionTier, TransactionDirection
from app.models.merchant_override import MerchantOverride
from app.models.user import User

# Ordered: first matching pattern wins. Tuned toward the kind of spend seen
# in a real student UPI-heavy statement (small local merchants), not a
# salaried professional's statement with rent/EMI -- extend this list as
# real data surfaces more patterns.
#
# KNOWN GAP: the TransactionCategory enum (rent/emi/groceries/utilities/
# food_delivery/shopping/entertainment/transfer/income/other) has no
# healthcare or education/stationery category. Medical and
# stationery/xerox spend below are bucketed into "shopping" as the closest
# fit for now. If this matters for your resume demo, it needs a new
# Alembic migration to add categories to the enum -- flag it to me if you
# want that done before this gets re-skinned as a dashboard.
KEYWORD_RULES: list[tuple[re.Pattern, TransactionCategory]] = [
    (re.compile(r"super\s*market|provision|kirana|grocer", re.IGNORECASE), TransactionCategory.groceries),
    # "medi" (not just "medical") because PDF column-width truncation cuts
    # "Medical" down to "Medi" in real statement data -- confirmed against
    # an actual transaction ("...dharshan medi"). Narrower words would miss it.
    (re.compile(r"\bmedi|pharmacy|chemist", re.IGNORECASE), TransactionCategory.shopping),  # see gap note above
    (re.compile(r"xerox|stationery|book\s*store|print", re.IGNORECASE), TransactionCategory.shopping),  # see gap note above
    (re.compile(r"juice|bakery|restaurant|food|zomato|swiggy|cafe|hotel", re.IGNORECASE), TransactionCategory.food_delivery),
    (re.compile(r"\brent\b|landlord", re.IGNORECASE), TransactionCategory.rent),
    (re.compile(r"\bemi\b|loan", re.IGNORECASE), TransactionCategory.emi),
    (re.compile(r"electricity|water\s*bill|broadband|recharge|utilit", re.IGNORECASE), TransactionCategory.utilities),
    (re.compile(r"netflix|prime\s*video|hotstar|spotify|bookmyshow|movie", re.IGNORECASE), TransactionCategory.entertainment),
    (re.compile(r"salary|stipend|refund|cashback", re.IGNORECASE), TransactionCategory.income),
]


def match_keyword_category(merchant_normalized: str) -> TransactionCategory:
    for pattern, category in KEYWORD_RULES:
        if pattern.search(merchant_normalized):
            return category
    return TransactionCategory.other


def compute_tier_from_amount(amount: Decimal, tier_thresholds: dict) -> TransactionTier:
    """
    tier_thresholds is the user's own fallback config, e.g.
    {"primary": 10000, "secondary": 5000}. Only ever called for debit
    transactions -- see the invariant note at the top of this file.
    """
    primary_threshold = Decimal(str(tier_thresholds.get("primary", 10000)))
    secondary_threshold = Decimal(str(tier_thresholds.get("secondary", 5000)))

    if amount >= primary_threshold:
        return TransactionTier.primary
    elif amount >= secondary_threshold:
        return TransactionTier.secondary
    else:
        return TransactionTier.tertiary


def classify_transaction(
    db: Session,
    user: User,
    merchant_normalized: str,
    amount: Decimal,
    direction: TransactionDirection,
) -> tuple[TransactionCategory, TransactionTier]:
    """
    Runs the full 3-step classification. Returns (category, tier) -- does
    NOT write anything to the DB; the caller assigns these to a Transaction.
    """
    override = (
        db.query(MerchantOverride)
        .filter(
            MerchantOverride.user_id == user.id,
            MerchantOverride.merchant_normalized == merchant_normalized,
        )
        .first()
    )

    if override is not None:
        category = override.category
        if direction == TransactionDirection.credit:
            tier = TransactionTier.not_applicable
        else:
            tier = override.tier
    else:
        category = match_keyword_category(merchant_normalized)
        if direction == TransactionDirection.credit:
            tier = TransactionTier.not_applicable
        else:
            tier = compute_tier_from_amount(amount, user.tier_thresholds or {})

    return category, tier
