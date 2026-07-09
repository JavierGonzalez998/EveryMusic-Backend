import uuid
from datetime import date, datetime

from sqlalchemy import Column, DateTime, func
from sqlmodel import Field, SQLModel


def uuid_pk() -> str:
    return Field(default_factory=lambda: str(uuid.uuid4()), max_length=36, primary_key=True)


# SQLAlchemy fills these itself — created_at via DB server_default, updated_at bumped onupdate.
# A fresh Column per call: the same Column instance can't be shared across tables.
def created_at_col():
    return Field(sa_column=Column(DateTime, server_default=func.now(), nullable=False))


def updated_at_col():
    return Field(
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class User(SQLModel, table=True):
    __tablename__ = "users"

    idUser: str = uuid_pk()
    name: str = Field(max_length=100)
    nickname: str = Field(max_length=50)
    email: str = Field(max_length=150, unique=True)
    passwd: str = Field(max_length=200)
    token_version: int = Field(default=0)  # bumped on logout to revoke all issued tokens
    email_verified: bool = Field(default=False)
    created_at: datetime = created_at_col()
    updated_at: datetime = updated_at_col()


class File(SQLModel, table=True):
    __tablename__ = "files"

    idFile: str = uuid_pk()
    ext: str = Field(max_length=8)
    uploaded_by: str = Field(foreign_key="users.idUser", max_length=36)
    size: int = Field(default=0)  # bytes of the audio, summed for the per-user quota
    has_cover: bool = Field(default=False)  # embedded album art stored at {user}/{file}.cover
    created_at: datetime = created_at_col()


class Playlist(SQLModel, table=True):
    __tablename__ = "playlists"

    idPlaylist: str = uuid_pk()
    name: str = Field(max_length=200)
    created_by: str = Field(foreign_key="users.idUser", max_length=36)
    is_public: bool = Field(default=False)  # public playlists are readable by anyone with the id
    created_at: datetime = created_at_col()
    updated_at: datetime = updated_at_col()


class PlaylistFile(SQLModel, table=True):
    __tablename__ = "playlist_files"

    idPlaylist: str = Field(foreign_key="playlists.idPlaylist", max_length=36, primary_key=True)
    idFile: str = Field(foreign_key="files.idFile", max_length=36, primary_key=True)
    position: int = Field(default=0)


class Favorite(SQLModel, table=True):
    __tablename__ = "favorites"

    idUser: str = Field(foreign_key="users.idUser", max_length=36, primary_key=True)
    idFile: str = Field(foreign_key="files.idFile", max_length=36, primary_key=True)
    created_at: datetime = created_at_col()


class PlayEvent(SQLModel, table=True):
    __tablename__ = "play_events"

    idEvent: str = uuid_pk()
    idUser: str = Field(foreign_key="users.idUser", max_length=36)
    idFile: str = Field(foreign_key="files.idFile", max_length=36)
    played_at: datetime = created_at_col()


class Device(SQLModel, table=True):
    __tablename__ = "devices"

    idDevice: str = uuid_pk()
    code: str = Field(max_length=12, unique=True, index=True)  # pairing code shown on the gadget
    token_hash: str = Field(max_length=200)  # hashed device secret (gadget's long-lived credential)
    idUser: str | None = Field(default=None, foreign_key="users.idUser", max_length=36)  # null until linked
    name: str | None = Field(default=None, max_length=100)
    created_at: datetime = created_at_col()


class Metadata(SQLModel, table=True):
    __tablename__ = "metadata"

    idMetadata: str = uuid_pk()
    idFile: str = Field(foreign_key="files.idFile", max_length=36)
    songName: str | None = Field(default=None, max_length=250)
    songArtist: str | None = Field(default=None, max_length=250)
    duration: str | None = Field(default=None, max_length=50)
    albumName: str | None = Field(default=None, max_length=100)
    publishDate: date | None = None
