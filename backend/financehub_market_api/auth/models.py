from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, String, func

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class UserRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)


class UserLoginRequest(BaseModel):
    email: str
    password: str


class UserInfo(BaseModel):
    id: str
    email: str
    created_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


def user_to_info(user: User) -> UserInfo:
    created = user.created_at
    if isinstance(created, datetime):
        iso = created.replace(tzinfo=UTC).isoformat() if created.tzinfo is None else created.isoformat()
    else:
        iso = str(created)
    return UserInfo(id=user.id, email=user.email, created_at=iso)
