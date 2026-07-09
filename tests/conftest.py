import io
import os
import struct
import wave

# Dummy env so config.Settings() validates at import (real .env values are overridden by these).
os.environ.setdefault("JWT_SECRET", "test-secret-0123456789abcdef0123456789")
os.environ.setdefault("MYSQL_URL", "mysql://u:p@localhost/test")
os.environ.setdefault("AWS_S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import controller.files.router as files_router
import models  # noqa: F401 — register tables on SQLModel.metadata
from db import get_session
from main import app
from ratelimit import limiter

# In-memory SQLite shared across connections; FK enforcement on (matches MySQL behaviour).
test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


@event.listens_for(test_engine, "connect")
def _fk_pragma(conn, _rec):
    conn.execute("PRAGMA foreign_keys=ON")


@pytest.fixture(autouse=True)
def _db():
    SQLModel.metadata.create_all(test_engine)
    app.dependency_overrides[get_session] = _session
    limiter.enabled = False  # otherwise repeated /login in tests would hit the 5/min cap
    yield
    app.dependency_overrides.clear()
    SQLModel.metadata.drop_all(test_engine)


def _session():
    with Session(test_engine) as s:
        yield s


@pytest.fixture
def store(monkeypatch):
    """Fake bucket: records objects by key so tests can assert upload/delete."""
    objects = {}
    monkeypatch.setattr(files_router, "upload", lambda k, d, ct: objects.update({k: d}) or k)
    monkeypatch.setattr(files_router, "delete_object", lambda k: objects.pop(k, None))
    monkeypatch.setattr(files_router, "presigned_url", lambda k, expires=3600: f"https://fake/{k}")
    return objects


@pytest.fixture
def mailbox(monkeypatch):
    """Capture emails so tests can pull verify/reset tokens out of the body."""
    import controller.users.router as users_router

    box = []
    monkeypatch.setattr(
        users_router, "send_email", lambda to, subject, body: box.append(body)
    )
    return box


@pytest.fixture
def db_session():
    with Session(test_engine) as s:
        yield s


@pytest.fixture
def wav():
    return wav_bytes


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth(client):
    """Factory: create a fresh user, return (auth headers, user id)."""
    counter = {"n": 0}

    def _make():
        counter["n"] += 1
        email = f"u{counter['n']}@test.co"
        client.post(
            "/register",
            json={"name": "x", "nickname": "x", "email": email, "password": "secret123"},
        )
        tok = client.post(
            "/login", data={"username": email, "password": "secret123"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}
        uid = client.get("/users/me", headers=headers).json()["idUser"]
        return headers, uid

    return _make


def wav_bytes(seconds: float = 0.1) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        n = int(8000 * seconds)
        w.writeframes(struct.pack(f"<{n}h", *([0] * n)))
    return b.getvalue()
