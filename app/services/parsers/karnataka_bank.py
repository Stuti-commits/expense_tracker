"""
Parser for Karnataka Bank (KBL) passbook/statement PDFs.

Rewritten against a REAL extracted statement (previous version was a blind
guess and was wrong — kept here as a record of what the actual format is,
in case KBL changes their export format later and this needs revisiting).

CONFIRMED REAL FORMAT:
    Opening Balance <amount>
    <DD-MM-YYYY> <narration ...> <amount> <balance>
    ...
    Closing Balance <amount>

Key facts about this format, confirmed from a real sample:
- Each transaction line has exactly ONE amount (not separate debit/credit
  columns) followed by the running balance after that transaction.
- There is NO debit/credit marker anywhere in the line. Direction must be
  inferred from whether the balance went up or down vs. the previous line.
- Narration text is truncated by the PDF's column width (e.g. a merchant
  name gets cut off mid-word). This truncation is consistent for the same
  merchant across multiple lines, so it's still usable for merchant
  matching later -- just don't expect full merchant names here.
- "Opening Balance" and "Closing Balance" lines have no date and are not
  transactions -- they're used only to seed/sanity-check the running balance.
"""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.services.parsers.base import ParsedLine, Direction, ParseError

DATE_PATTERN = r"(\d{2}-\d{2}-\d{4})"
AMOUNT_PATTERN = r"([\d,]+\.\d{2})"

# A transaction line: date, narration (non-greedy), amount, balance. Exactly
# two trailing numbers -- confirmed against a real statement, not a guess.
TRANSACTION_LINE = re.compile(
    rf"^{DATE_PATTERN}\s+(.+?)\s+{AMOUNT_PATTERN}\s+{AMOUNT_PATTERN}$"
)

OPENING_BALANCE_LINE = re.compile(rf"^Opening Balance\s+{AMOUNT_PATTERN}$")
CLOSING_BALANCE_LINE = re.compile(rf"^Closing Balance\s+{AMOUNT_PATTERN}$")

# Allow a tiny rounding tolerance when reconciling balance deltas.
RECONCILE_TOLERANCE = Decimal("0.01")


def _parse_amount(raw: str) -> Decimal:
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        raise ParseError(f"Could not parse amount: {raw!r}")


def _parse_date(raw: str):
    try:
        return datetime.strptime(raw, "%d-%m-%Y").date()
    except ValueError:
        raise ParseError(f"Could not parse date: {raw!r}")


def parse(text: str) -> list[ParsedLine]:
    """
    Parses raw extracted statement text into a list of ParsedLine.

    Direction is determined by comparing each line's balance to the running
    balance (seeded from "Opening Balance"). For each row:
      - if running_balance - amount == new_balance  -> debit
      - if running_balance + amount == new_balance  -> credit
      - if neither reconciles (within rounding tolerance) -> the row is
        SKIPPED, not guessed. This usually means a line got mangled by PDF
        text extraction (merged/split across a page break, etc.) -- better
        to surface as a gap than silently mislabel a transaction's direction.

    Always check len(result) against the actual number of transaction rows
    in the PDF (count them yourself) before trusting this blindly -- rows
    that fail to reconcile are dropped silently from the returned list.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    running_balance = None
    results: list[ParsedLine] = []
    skipped_count = 0

    for line in lines:
        if line == "--- PAGE BREAK ---":
            continue

        opening_match = OPENING_BALANCE_LINE.match(line)
        if opening_match:
            running_balance = _parse_amount(opening_match.group(1))
            continue

        closing_match = CLOSING_BALANCE_LINE.match(line)
        if closing_match:
            continue

        match = TRANSACTION_LINE.match(line)
        if not match:
            continue  # header, footer, page number, address block, etc.

        date_str, narration, amount_str, balance_str = match.groups()

        try:
            tx_date = _parse_date(date_str)
            amount = _parse_amount(amount_str)
            new_balance = _parse_amount(balance_str)
        except ParseError:
            skipped_count += 1
            continue

        if running_balance is None:
            skipped_count += 1
            continue

        if abs((running_balance - amount) - new_balance) <= RECONCILE_TOLERANCE:
            direction = Direction.debit
        elif abs((running_balance + amount) - new_balance) <= RECONCILE_TOLERANCE:
            direction = Direction.credit
        else:
            skipped_count += 1
            running_balance = new_balance
            continue

        results.append(
            ParsedLine(
                date=tx_date,
                narration_raw=narration.strip(),
                amount=amount,
                direction=direction,
            )
        )
        running_balance = new_balance

    if skipped_count:
        import sys
        print(
            f"[karnataka_bank parser] WARNING: skipped {skipped_count} line(s) "
            f"that looked like transactions but couldn't be parsed/reconciled.",
            file=sys.stderr,
        )

    return results
