from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException

LOGGER = logging.getLogger(__name__)

_JWT_ALGORITHM = "HS256"


def _get_jwt_secret() -> str:
    secret = os.environ.get("FINANCEHUB_JWT_SECRET_KEY", "")
    if not secret:
        LOGGER.warning("FINANCEHUB_JWT_SECRET_KEY is not set — using insecure default for development")
        return "dev-insecure-secret-change-me"
    return secret


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str


def get_current_user(
    authorization: str = Header(default=""),
) -> AuthenticatedUser:
    """Decode JWT from ``Authorization: Bearer <token>`` header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[len("Bearer ") :]
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    email = payload.get("email", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return AuthenticatedUser(user_id=user_id, email=email)
