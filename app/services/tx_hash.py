"""
Computes the dedup hash for a single parsed transaction.

Deliberately does NOT include statement_id. If it did, re-uploading a
statement with an overlapping date range (a real, expected scenario --
e.g. uploading Sept 1-30, then later Oct 1-31 where the bank's export
overlaps by a few days) would hash every transaction differently each
time, and duplicate rows would never be caught. Hashing on the
transaction's own content instead means the SAME real-world transaction
gets the SAME hash no matter which statement upload it came from.

Uses merchant_raw (not merchant_normalized) specifically because it still
contains the per-transaction reference number -- this is what stops two
separate, legitimate same-day/same-amount/same-merchant transactions from
colliding into one.

user_id is included because the hash has no other way to stay scoped per
user -- without it, two different users' statements could theoretically
produce an identical hash for an unrelated transaction (same date, same
amount, same merchant) and incorrectly block one of them.
"""

import hashlib
from datetime import date
from decimal import Decimal


def compute_tx_hash(
    user_id: str,
    tx_date: date,
    amount: Decimal,
    direction: str,
    merchant_raw: str,
) -> str:
    raw = f"{user_id}|{tx_date.isoformat()}|{amount}|{direction}|{merchant_raw.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
