"""
Maps a bank_name string (what the client sends on upload) to its parser
module's `parse` function. Adding bank #2 later = write
app/services/parsers/<bank>.py with a `parse(text) -> list[ParsedLine]`
function, then add one line here. Nothing else changes.
"""

from app.services.parsers import karnataka_bank
from app.services.parsers.base import ParsedLine

PARSERS = {
    "karnataka_bank": karnataka_bank.parse,
}


def get_parser(bank_name: str):
    parser_fn = PARSERS.get(bank_name)
    if parser_fn is None:
        raise ValueError(
            f"No parser available for bank_name={bank_name!r}. "
            f"Supported: {list(PARSERS.keys())}"
        )
    return parser_fn
