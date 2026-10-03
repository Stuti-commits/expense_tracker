"""
Decrypts a password-protected PDF entirely in memory.

Design rule (non-negotiable, per the privacy decision made earlier in this
project): the password is used exactly once, in this function, and never
written to disk, logged, or stored on the `statements` row. The caller is
responsible for not holding onto it either — see the router, which reads it
from the request and lets it go out of scope immediately after this call.
"""

import io

import pikepdf
from fastapi import HTTPException, status


class PDFDecryptError(Exception):
    """Raised when a PDF can't be decrypted — wrong password or corrupt file."""


def decrypt_pdf_bytes(file_bytes: bytes, password: str) -> bytes:
    """
    Takes the raw encrypted PDF bytes and a password.
    Returns the decrypted PDF as bytes (in memory, never written to disk).

    Note: Python cannot guarantee a string is scrubbed from memory the instant
    you're done with it (that's a C-level guarantee this language doesn't give
    you) — so "discard the password" here means: don't store it, don't log it,
    don't pass it anywhere beyond this function, and let it go out of scope
    as soon as this call returns. That's the realistic bar for a web app;
    true memory-scrubbing would need a lower-level language.
    """
    try:
        with pikepdf.open(io.BytesIO(file_bytes), password=password) as pdf:
            output_buffer = io.BytesIO()
            # Save WITHOUT a password — this in-memory copy is decrypted,
            # and it's never written to disk, only passed to the text extractor.
            pdf.save(output_buffer)
            return output_buffer.getvalue()
    except pikepdf.PasswordError:
        raise PDFDecryptError("Incorrect password for this PDF.")
    except pikepdf.PdfError as e:
        raise PDFDecryptError(f"Could not open PDF — it may be corrupt: {e}")


def decrypt_pdf_or_422(file_bytes: bytes, password: str) -> bytes:
    """
    Convenience wrapper for routers: decrypts or raises a clean HTTP 422
    instead of leaking a raw exception to the client.
    """
    try:
        return decrypt_pdf_bytes(file_bytes, password)
    except PDFDecryptError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
