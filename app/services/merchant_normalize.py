"""
Turns a raw narration string into a merchant_normalized string suitable for
grouping/matching (merchant_overrides lookups in the next phase).

Bank-specific because every bank's narration format is different -- same
pattern as app/services/parsers/registry.py. Add a new bank's normalizer
function here and register it in NORMALIZERS; nothing else changes.

IMPORTANT: this is deliberately separate from merchant_raw, which is used
for tx_hash (dedup) instead. merchant_raw keeps the transaction-unique
reference number so two separate same-day/same-amount/same-merchant
transactions don't collide. merchant_normalized strips that reference
number specifically so the SAME merchant across different transactions
groups together for classification. Never use merchant_normalized for
dedup, and never use merchant_raw for classification grouping.
"""

import re

# Karnataka Bank narrations look like:
#   UPI:624686519622:q74679871@ybl(Sapna Super market
# The digits after "UPI:" are a per-transaction reference number -- unique
# every time, even for the same merchant. Stripping it is what makes
# repeated visits to the same merchant normalize to an identical string.
_KBL_UPI_PREFIX = re.compile(r"^UPI:\d+:")


def normalize_karnataka_bank(narration_raw: str) -> str:
    cleaned = _KBL_UPI_PREFIX.sub("", narration_raw)
    return cleaned.strip().lower()


def normalize_default(narration_raw: str) -> str:
    """Fallback for banks without a specific normalizer yet: just trim/lowercase."""
    return narration_raw.strip().lower()


NORMALIZERS = {
    "karnataka_bank": normalize_karnataka_bank,
}


def normalize_merchant(bank_name: str, narration_raw: str) -> str:
    normalizer = NORMALIZERS.get(bank_name, normalize_default)
    return normalizer(narration_raw)
