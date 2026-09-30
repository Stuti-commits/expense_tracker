"""
FastAPI dependencies for auth. Use `get_current_user` on any route that
requires a logged-in user — it handles extracting the token from the
Authorization header and verifying it with Firebase.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.firebase import verify_firebase_token

# Expects: Authorization: Bearer <firebase_id_token>
bearer_scheme = HTTPBearer()


class CurrentUser:
    """Lightweight wrapper around the decoded Firebase token."""

    def __init__(self, decoded_token: dict):
        self.uid: str = decoded_token["uid"]
        self.email: str | None = decoded_token.get("email")
        self.raw = decoded_token


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    """
    Drop this into any route as: `user: CurrentUser = Depends(get_current_user)`.
    FastAPI will 401 automatically before your route body even runs if the
    token is missing or invalid.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
        )
    decoded_token = verify_firebase_token(credentials.credentials)
    return CurrentUser(decoded_token)
