"""
Shared contract every bank parser must follow.

Adding a new bank later = one new file in this folder implementing
`parse(text: str) -> list[ParsedLine]`, plus one line in parser_registry.py.
Nothing else in the pipeline changes.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class Direction(str, Enum):
    debit = "debit"
    credit = "credit"


@dataclass
class ParsedLine:
    """
    One transaction row as read off the statement — before merchant
    normalization or classification. This is intentionally "dumb": it
    just mirrors what's literally printed on the statement line.
    """
    date: date
    narration_raw: str
    amount: Decimal
    direction: Direction


class ParseError(Exception):
    """Raised when a parser cannot make sense of the extracted text at all —
    e.g. the text doesn't match the expected statement format for that bank."""
