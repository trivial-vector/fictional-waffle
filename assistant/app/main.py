from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings
from app.db.graph import init_graph
from app.db.postgres import close_pool, init_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    init_graph(settings.kuzu_db_path)
    yield
    await close_pool()


app = FastAPI(title="Assistant Long-Term Memory", lifespan=lifespan)

# Prototype-scope CORS: wide open. Fine for a single-user local deployment;
# tighten before exposing this beyond localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

# The web UI (chat + memory browser) is served directly from this container
# so the main chat/memory calls never cross an origin — only the separate
# voice-transcription service (a different container/port) needs the CORS
# middleware above. See web/ and docker-compose.yml.
#
# settings.web_dir (default /web) matches where the Dockerfile copies the
# repo's web/ directory inside the image. Falls back to a path relative to
# this repo for running outside Docker directly from the repo root.
_web_dir_candidates = [Path(settings.web_dir), Path(__file__).resolve().parent.parent.parent / "web"]
_web_dir = next((p for p in _web_dir_candidates if p.exists()), None)
if _web_dir is not None:
    app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="web")
