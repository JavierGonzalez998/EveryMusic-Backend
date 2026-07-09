import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlmodel import Session, select

from controller.auth.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from db import get_session
from models import Device, User
from ratelimit import limiter

router = APIRouter()


class RegisterOut(BaseModel):
    idDevice: str
    code: str
    device_token: str  # shown once — the gadget stores it to authenticate later


class LinkIn(BaseModel):
    code: str
    name: str | None = None


class DeviceAuthIn(BaseModel):
    idDevice: str
    device_token: str


class DeviceOut(BaseModel):
    idDevice: str
    name: str | None
    linked: bool


@router.post("/devices/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def register_device(request: Request, session: Session = Depends(get_session)):
    """Called by the gadget on first boot: mint a pairing code + a long-lived secret."""
    code = secrets.token_hex(4).upper()
    while session.exec(select(Device).where(Device.code == code)).first():
        code = secrets.token_hex(4).upper()
    raw = secrets.token_urlsafe(32)
    dev = Device(code=code, token_hash=hash_password(raw))
    session.add(dev)
    session.commit()
    session.refresh(dev)
    return RegisterOut(idDevice=dev.idDevice, code=code, device_token=raw)


@router.post("/devices/link")
def link_device(
    data: LinkIn,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Called by the user's app: claim a pending device by its code."""
    dev = session.exec(select(Device).where(Device.code == data.code)).first()
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown device code")
    if dev.idUser and dev.idUser != current.idUser:
        raise HTTPException(status.HTTP_409_CONFLICT, "Device already linked")
    dev.idUser = current.idUser
    if data.name:
        dev.name = data.name
    session.add(dev)
    session.commit()
    return {"idDevice": dev.idDevice, "linked": True}


@router.post("/devices/auth")
def device_auth(data: DeviceAuthIn, session: Session = Depends(get_session)):
    """Called by the gadget (polling): exchange its secret for an access token once linked."""
    dev = session.get(Device, data.idDevice)
    if not dev or not verify_password(data.device_token, dev.token_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid device credentials")
    if not dev.idUser:
        raise HTTPException(status.HTTP_425_TOO_EARLY, "Device not linked yet")
    user = session.get(User, dev.idUser)
    # Reuses the standard user access token → the gadget can call every playback endpoint.
    return {"access_token": create_access_token(user), "token_type": "bearer"}


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    devs = session.exec(select(Device).where(Device.idUser == current.idUser)).all()
    return [DeviceOut(idDevice=d.idDevice, name=d.name, linked=True) for d in devs]


@router.delete("/devices/{id_device}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_device(
    id_device: str,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    dev = session.get(Device, id_device)
    if not dev or dev.idUser != current.idUser:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    session.delete(dev)  # gadget can no longer exchange for new tokens
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
