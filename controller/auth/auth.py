from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from config import settings
from db import get_session
from models import User

ALGORITHM = "HS256"
ACCESS_TTL = timedelta(hours=settings.access_ttl_hours)
REFRESH_TTL = timedelta(days=settings.refresh_ttl_days)
VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(hours=1)

oauth2 = OAuth2PasswordBearer(tokenUrl="login")


def hash_password(pw: str) -> str:
    # bcrypt caps at 72 bytes; truncate so long passwords don't raise.
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode()[:72], hashed.encode())


def _make(user: User, kind: str, ttl: timedelta) -> str:
    payload = {
        "sub": user.idUser,
        "type": kind,
        "ver": user.token_version,  # invalidated when the user logs out
        "exp": datetime.now(timezone.utc) + ttl,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_access_token(user: User) -> str:
    return _make(user, "access", ACCESS_TTL)


def create_refresh_token(user: User) -> str:
    return _make(user, "refresh", REFRESH_TTL)


def create_verify_token(user: User) -> str:
    return _make(user, "verify", VERIFY_TTL)


def create_reset_token(user: User) -> str:
    return _make(user, "reset", RESET_TTL)


def _decode(token: str, expected_type: str, session: Session) -> User:
    err = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise err
    if payload.get("type") != expected_type:
        raise err
    user = session.get(User, payload.get("sub"))
    if not user or payload.get("ver") != user.token_version:
        raise err
    return user


def get_current_user(
    token: str = Depends(oauth2), session: Session = Depends(get_session)
) -> User:
    return _decode(token, "access", session)


def user_from_refresh(token: str, session: Session) -> User:
    return _decode(token, "refresh", session)


def user_from_verify(token: str, session: Session) -> User:
    return _decode(token, "verify", session)


def user_from_reset(token: str, session: Session) -> User:
    return _decode(token, "reset", session)
