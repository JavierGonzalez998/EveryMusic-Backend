from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from controller.auth.auth import (
    create_access_token,
    create_refresh_token,
    create_reset_token,
    create_verify_token,
    get_current_user,
    hash_password,
    user_from_refresh,
    user_from_reset,
    user_from_verify,
    verify_password,
)
from config import settings
from db import get_session
from email_util import send_email
from models import User
from ratelimit import limiter

router = APIRouter()


class UserCreate(BaseModel):
    name: str
    nickname: str
    email: EmailStr
    password: str


class UserOut(BaseModel):
    idUser: str
    name: str
    nickname: str
    email: str
    email_verified: bool

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class VerifyIn(BaseModel):
    token: str


class ResetRequestIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    new_password: str


class UserUpdate(BaseModel):
    name: str | None = None
    nickname: str | None = None
    email: EmailStr | None = None
    password: str | None = None


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def register(request: Request, data: UserCreate, session: Session = Depends(get_session)):
    if session.exec(select(User).where(User.email == data.email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        name=data.name,
        nickname=data.nickname,
        email=data.email,
        passwd=hash_password(data.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    user = session.exec(select(User).where(User.email == form.username)).first()
    if not user or not verify_password(form.password, user.passwd):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    return Token(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
    )


@router.post("/refresh", response_model=Token)
def refresh(data: RefreshIn, session: Session = Depends(get_session)):
    user = user_from_refresh(data.refresh_token, session)
    return Token(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current: User = Depends(get_current_user), session: Session = Depends(get_session)):
    current.token_version += 1  # revokes every access + refresh token already issued
    session.add(current)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return current


@router.patch("/users/me", response_model=UserOut)
def update_me(
    data: UserUpdate,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if data.email and data.email != current.email:
        if session.exec(select(User).where(User.email == data.email)).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        current.email = data.email
    if data.name is not None:
        current.name = data.name
    if data.nickname is not None:
        current.nickname = data.nickname
    if data.password:
        current.passwd = hash_password(data.password)
        current.token_version += 1  # changing the password logs out every existing session
    session.add(current)
    session.commit()
    session.refresh(current)
    return current


@router.post("/auth/request-verify", status_code=status.HTTP_202_ACCEPTED)
def request_verify(current: User = Depends(get_current_user)):
    token = create_verify_token(current)
    link = f"{settings.app_base_url}/verify-email?token={token}"
    send_email(current.email, "Verify your email", f"Confirm your email: {link}")
    return {"detail": "Verification email sent"}


@router.post("/auth/verify")
def verify_email(data: VerifyIn, session: Session = Depends(get_session)):
    user = user_from_verify(data.token, session)
    user.email_verified = True
    session.add(user)
    session.commit()
    return {"email_verified": True}


@router.post("/auth/request-password-reset", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
def request_password_reset(
    request: Request, data: ResetRequestIn, session: Session = Depends(get_session)
):
    user = session.exec(select(User).where(User.email == data.email)).first()
    if user:  # silent when the email is unknown — don't leak which addresses exist
        token = create_reset_token(user)
        link = f"{settings.app_base_url}/reset-password?token={token}"
        send_email(user.email, "Reset your password", f"Reset your password: {link}")
    return {"detail": "If the email exists, a reset link was sent"}


@router.post("/auth/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(data: ResetIn, session: Session = Depends(get_session)):
    user = user_from_reset(data.token, session)
    user.passwd = hash_password(data.new_password)
    user.token_version += 1  # invalidates the reset token and every existing session
    session.add(user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
