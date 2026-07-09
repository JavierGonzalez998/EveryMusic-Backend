from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlmodel import Session, func, select

from controller.auth.auth import get_current_user
from db import get_session
from models import File as FileModel
from models import Metadata, Playlist, PlaylistFile, User

router = APIRouter()


def _owned_playlist(session: Session, id_playlist: str, user: User) -> Playlist:
    pl = session.get(Playlist, id_playlist)
    if not pl or pl.created_by != user.idUser:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist not found")
    return pl


class PlaylistCreate(BaseModel):
    name: str


class PlaylistOut(BaseModel):
    idPlaylist: str
    name: str
    created_by: str
    is_public: bool

    model_config = {"from_attributes": True}


class PlaylistUpdate(BaseModel):
    name: str | None = None
    is_public: bool | None = None


class AddFiles(BaseModel):
    idFiles: list[str]


@router.post("/playlists", response_model=PlaylistOut, status_code=status.HTTP_201_CREATED)
def create_playlist(
    data: PlaylistCreate,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    pl = Playlist(name=data.name, created_by=current.idUser)
    session.add(pl)
    session.commit()
    session.refresh(pl)
    return pl


@router.get("/playlists", response_model=list[PlaylistOut])
def list_playlists(
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(Playlist).where(Playlist.created_by == current.idUser)
    ).all()


@router.get("/playlists/{id_playlist}")
def get_playlist(
    id_playlist: str,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    pl = session.get(Playlist, id_playlist)
    if not pl or (pl.created_by != current.idUser and not pl.is_public):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist not found")
    rows = session.exec(
        select(PlaylistFile)
        .where(PlaylistFile.idPlaylist == id_playlist)
        .order_by(PlaylistFile.position)
    ).all()
    tracks = []
    for pf in rows:  # ponytail: N+1 per track, fine at this scale
        f = session.get(FileModel, pf.idFile)
        meta = session.exec(select(Metadata).where(Metadata.idFile == pf.idFile)).first()
        tracks.append({"position": pf.position, "file": f, "metadata": meta})
    return {"playlist": pl, "tracks": tracks}


@router.patch("/playlists/{id_playlist}", response_model=PlaylistOut)
def update_playlist(
    id_playlist: str,
    data: PlaylistUpdate,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    pl = _owned_playlist(session, id_playlist, current)
    if data.name is not None:
        pl.name = data.name
    if data.is_public is not None:
        pl.is_public = data.is_public
    session.add(pl)
    session.commit()
    session.refresh(pl)
    return pl


@router.post("/playlists/{id_playlist}/files", status_code=status.HTTP_201_CREATED)
def add_files(
    id_playlist: str,
    data: AddFiles,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _owned_playlist(session, id_playlist, current)

    # Next position appends after the current tail.
    next_pos = (
        session.exec(
            select(func.max(PlaylistFile.position)).where(
                PlaylistFile.idPlaylist == id_playlist
            )
        ).one()
        or 0
    ) + 1

    added, skipped = [], []
    for fid in data.idFiles:
        f = session.get(FileModel, fid)
        if not f or f.uploaded_by != current.idUser:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File {fid} not found or not yours")
        if session.get(PlaylistFile, (id_playlist, fid)):
            skipped.append(fid)  # already in playlist — idempotent
            continue
        session.add(PlaylistFile(idPlaylist=id_playlist, idFile=fid, position=next_pos))
        next_pos += 1
        added.append(fid)

    session.commit()
    return {"idPlaylist": id_playlist, "added": added, "skipped": skipped}


@router.delete("/playlists/{id_playlist}/files/{id_file}", status_code=status.HTTP_204_NO_CONTENT)
def remove_file(
    id_playlist: str,
    id_file: str,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _owned_playlist(session, id_playlist, current)
    pf = session.get(PlaylistFile, (id_playlist, id_file))
    if not pf:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not in playlist")
    session.delete(pf)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/playlists/{id_playlist}", status_code=status.HTTP_204_NO_CONTENT)
def delete_playlist(
    id_playlist: str,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    pl = _owned_playlist(session, id_playlist, current)
    for pf in session.exec(
        select(PlaylistFile).where(PlaylistFile.idPlaylist == id_playlist)
    ).all():
        session.delete(pf)
    session.flush()  # junction rows gone before the parent — FK order isn't inferred without relationship()
    session.delete(pl)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
