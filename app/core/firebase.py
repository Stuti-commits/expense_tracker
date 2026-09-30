"""
Firebase Admin SDK setup.

This module does exactly two things:
1. Initializes the Firebase Admin app once (using a service account key).
2. Exposes a function to verify an incoming ID token and return the decoded
   Firebase user info (uid, email, etc.).

It does NOT handle login/signup — that happens on the client (web/mobile app)
using the Firebase client SDK. The backend only ever verifies tokens that the
client already obtained from Firebase.
"""

import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
from fastapi import HTTPException, status

from app.core.config import settings

# Initialize the Firebase app exactly once, even if this module gets imported
# multiple times (FastAPI reload, tests, etc.)
if not firebase_admin._apps:
    cred = credentials.Certificate(settings.firebase_credentials_path)
    firebase_admin.initialize_app(cred)


def verify_firebase_token(id_token: str) -> dict:
    """
    Verifies a Firebase ID token sent by the client.

    Raises HTTP 401 if the token is missing, expired, or invalid.
    Returns the decoded token dict on success — the field you'll use most
    is decoded_token["uid"], which becomes your users.id / user_id foreign key
    everywhere in Postgres.
    """
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        return decoded_token
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase token has expired. Please sign in again.",
        )
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token.",
        )
    except Exception:
        # Catch-all so a malformed token never leaks a raw stack trace to the client.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
        )
