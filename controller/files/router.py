import io
from datetime import datetime

import mutagen
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlmodel import Session, func, or_, select

from controller.auth.auth import get_current_user
from db import get_session
from models import Favorite
from models import File as FileModel
from models import Metadata, PlaylistFile, PlayEvent, User
from storage import delete as delete_object
from storage import presigned_url, upload

router = APIRouter()

ALLOWED = {"mp3": "audio/mpeg", "flac": "audio/flac", "wav": "audio/wav"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB per file
USER_QUOTA_BYTES = 600 * 1024 * 1024  # 600 MB total per user


def _parse_date(s):
    if not s:
        return None
    s = str(s).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _extract_metadata(audio) -> dict:
    def first(key):
        v = audio.get(key)
        return v[0] if v else None

    dur = getattr(audio.info, "length", None)
    return {
        "songName": first("title"),
        "songArtist": first("artist"),
        "albumName": first("album"),
        "duration": f"{dur:.2f}" if dur else None,
        "publishDate": _parse_date(first("date")),
    }


def _extract_cover(data: bytes):
    """Return (bytes, mime) of embedded album art, or None. Handles FLAC / ID3 / MP4."""
    audio = mutagen.File(io.BytesIO(data))
    if audio is None:
        return None
    pics = getattr(audio, "pictures", None)  # FLAC
    if pics:
        return pics[0].data, pics[0].mime or "image/jpeg"
    tags = getattr(audio, "tags", None)
    if tags:
        try:
            apics = tags.getall("APIC")  # ID3 / mp3
            if apics:
                return apics[0].data, apics[0].mime or "image/jpeg"
        except (AttributeError, KeyError):
            pass
        covr = tags.get("covr")  # mp4 / m4a
        if covr:
            fmt = "image/png" if covr[0].imageformat == covr[0].FORMAT_PNG else "image/jpeg"
            return bytes(covr[0]), fmt
    return None


def _with_metadata(session: Session, f: FileModel) -> dict:
    meta = session.exec(select(Metadata).where(Metadata.idFile == f.idFile)).first()
    return {"file": f, "metadata": meta}


@router.post("/files", status_code=status.HTTP_201_CREATED)
async def upload_audio(
    file: UploadFile = File(...),
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only .mp3, .flac or .wav allowed")

    # Read at most MAX+1 bytes so an oversized file never fully loads into memory.
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 50 MB)")

    audio = mutagen.File(io.BytesIO(data), easy=True)
    if audio is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is not valid audio")

    used = session.exec(
        select(func.coalesce(func.sum(FileModel.size), 0)).where(
            FileModel.uploaded_by == current.idUser
        )
    ).one()
    if used + len(data) > USER_QUOTA_BYTES:  # ponytail: counts audio bytes, not the small cover
        raise HTTPException(413, "Storage quota exceeded (600 MB per user)")

    row = FileModel(ext=ext, uploaded_by=current.idUser, size=len(data))
    # Upload to the bucket before committing — a storage failure leaves no orphan DB row.
    upload(f"{current.idUser}/{row.idFile}.{ext}", data, ALLOWED[ext])

    cover = _extract_cover(data)
    if cover:
        upload(f"{current.idUser}/{row.idFile}.cover", cover[0], cover[1])
        row.has_cover = True

    meta = Metadata(idFile=row.idFile, **_extract_metadata(audio))
    session.add(row)
    session.add(meta)
    session.commit()
    session.refresh(row)
    session.refresh(meta)
    return {"file": row, "metadata": meta}


@router.get("/files")
def list_files(
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
):
    rows = session.exec(
        select(FileModel)
        .where(FileModel.uploaded_by == current.idUser)
        .offset(offset)
        .limit(limit)
    ).all()
    return [_with_metadata(session, f) for f in rows]  # ponytail: N+1 on metadata, fine at this scale


@router.get("/search")
def search(
    q: str,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
):
    like = f"%{q}%"
    rows = session.exec(
        select(FileModel, Metadata)
        .join(Metadata, Metadata.idFile == FileModel.idFile)
        .where(FileModel.uploaded_by == current.idUser)
        .where(
            or_(
                Metadata.songName.ilike(like),
                Metadata.songArtist.ilike(like),
                Metadata.albumName.ilike(like),
            )
        )
        .offset(offset)
        .limit(limit)
    ).all()
    return [{"file": f, "metadata": m} for f, m in rows]


@router.get("/files/{id_file}")
def get_file(
    id_file: str,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    f = session.get(FileModel, id_file)
    if not f or f.uploaded_by != current.idUser:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return _with_metadata(session, f)


@router.delete("/files/{id_file}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    id_file: str,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    f = session.get(FileModel, id_file)
    if not f or f.uploaded_by != current.idUser:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")

    # Cascade by hand: junction rows + metadata + bucket object, then the file row.
    for pf in session.exec(select(PlaylistFile).where(PlaylistFile.idFile == id_file)).all():
        session.delete(pf)
    for m in session.exec(select(Metadata).where(Metadata.idFile == id_file)).all():
        session.delete(m)
    for fav in session.exec(select(Favorite).where(Favorite.idFile == id_file)).all():
        session.delete(fav)
    for ev in session.exec(select(PlayEvent).where(PlayEvent.idFile == id_file)).all():
        session.delete(ev)
    session.flush()  # children gone first — no relationship() so SQLAlchemy won't order the FK for us
    delete_object(f"{f.uploaded_by}/{f.idFile}.{f.ext}")  # before commit: failure aborts the delete
    if f.has_cover:
        delete_object(f"{f.uploaded_by}/{f.idFile}.cover")
    session.delete(f)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/files/{id_file}/play")
def play(
    id_file: str,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    f = session.get(FileModel, id_file)
    if not f or f.uploaded_by != current.idUser:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    session.add(PlayEvent(idUser=current.idUser, idFile=id_file))  # record for /history
    session.commit()
    key = f"{f.uploaded_by}/{f.idFile}.{f.ext}"
    return {"url": presigned_url(key), "expires_in": 3600}


@router.get("/files/{id_file}/cover")
def cover(
    id_file: str,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    f = session.get(FileModel, id_file)
    if not f or f.uploaded_by != current.idUser:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    if not f.has_cover:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No cover art")
    key = f"{f.uploaded_by}/{f.idFile}.cover"
    return {"url": presigned_url(key), "expires_in": 3600}


@router.get("/history")
def history(
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
):
    events = session.exec(
        select(PlayEvent)
        .where(PlayEvent.idUser == current.idUser)
        .order_by(PlayEvent.played_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        {"played_at": e.played_at, **_with_metadata(session, session.get(FileModel, e.idFile))}
        for e in events
    ]


@router.get("/favorites")
def list_favorites(
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
):
    favs = session.exec(
        select(Favorite)
        .where(Favorite.idUser == current.idUser)
        .offset(offset)
        .limit(limit)
    ).all()
    return [_with_metadata(session, session.get(FileModel, fav.idFile)) for fav in favs]


@router.post("/files/{id_file}/favorite", status_code=status.HTTP_201_CREATED)
def favorite(
    id_file: str,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    f = session.get(FileModel, id_file)
    if not f or f.uploaded_by != current.idUser:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    if not session.get(Favorite, (current.idUser, id_file)):  # idempotent
        session.add(Favorite(idUser=current.idUser, idFile=id_file))
        session.commit()
    return {"idFile": id_file, "favorited": True}


@router.delete("/files/{id_file}/favorite", status_code=status.HTTP_204_NO_CONTENT)
def unfavorite(
    id_file: str,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    fav = session.get(Favorite, (current.idUser, id_file))
    if fav:
        session.delete(fav)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
