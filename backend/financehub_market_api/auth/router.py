from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import AuthenticatedUser, _JWT_ALGORITHM, _get_jwt_secret, get_current_user
from .models import (
    AuthResponse,
    User,
    UserInfo,
    UserLoginRequest,
    UserRegisterRequest,
    user_to_info,
)

LOGGER = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _create_token(user: User) -> str:
    expire_hours = int(os.environ.get("FINANCEHUB_JWT_EXPIRE_HOURS", "24"))
    payload = {
        "sub": user.id,
        "email": user.email,
        "exp": datetime.now(UTC) + timedelta(hours=expire_hours),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=_JWT_ALGORITHM)


@auth_router.post("/register", response_model=AuthResponse)
def register(
    body: UserRegisterRequest,
    db: Annotated[Session, Depends(get_db)],
) -> AuthResponse:
    email = body.email.strip().lower()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        user = User(
            id=uuid4().hex,
            email=email,
            password_hash=_hash_password(body.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from None
    except OperationalError as exc:
        db.rollback()
        LOGGER.exception("Database error during register")
        raise HTTPException(
            status_code=503,
            detail=(
                "Database unavailable. Ensure MySQL is running, database `financehub` exists, "
                "and credentials match FINANCEHUB_MYSQL_URL (default: test/test123 on "
                "localhost:3306 — mysql+pymysql://test:test123@localhost:3306/financehub)."
            ),
        ) from exc

    token = _create_token(user)
    return AuthResponse(access_token=token, user=user_to_info(user))


@auth_router.post("/login", response_model=AuthResponse)
def login(
    body: UserLoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> AuthResponse:
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = _create_token(user)
    return AuthResponse(access_token=token, user=user_to_info(user))


@auth_router.get("/me", response_model=UserInfo)
def get_me(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> UserInfo:
    db_user = db.query(User).filter(User.id == user.user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return user_to_info(db_user)
