"""
Extracts raw text from a decrypted PDF, in memory.

ASSUMPTION THAT NEEDS VERIFYING ON YOUR END:
This assumes the PDF has selectable/extractable text (a normal digital
statement export). If your Karnataka Bank PDF is actually a scanned image
with no selectable text, pdfplumber will return empty or garbage strings
per page, and you'll need OCR (pytesseract) instead — a materially different
and heavier pipeline. Test this against a real file before building further
on top of it.
"""

import io

import pdfplumber


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Returns the full extracted text of the PDF, pages joined by a marker
    so a parser can still tell where page breaks were if that matters
    for its row-matching logic.
    """
    pages_text = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages_text.append(text)
    return "\n--- PAGE BREAK ---\n".join(pages_text)
