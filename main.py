import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session, text

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import settings
from db import get_session
from ratelimit import limiter
from controller.devices.router import router as devices_router
from controller.files.router import router as files_router
from controller.playlists.router import router as playlists_router
from controller.users.router import router as users_router

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("em-back")

if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(dsn=settings.sentry_dsn)

app = FastAPI()  # schema is managed by Alembic — run `alembic upgrade head`
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: comma-separated ALLOWED_ORIGINS, default "*" (we auth via Bearer header, not cookies).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(users_router)
app.include_router(files_router)
app.include_router(playlists_router)
app.include_router(devices_router)


@app.get("/health/db")
def health_db(session: Session = Depends(get_session)):
    session.exec(text("SELECT 1"))
    return {"db": "ok"}


@app.get("/")
def read_root():
    return {"msg": "Hey! What are you doing here!? "}