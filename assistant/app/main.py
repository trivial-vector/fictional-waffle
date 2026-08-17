from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

# The web UI (web/) runs as its own standalone container — possibly on a
# different host entirely — so every call it makes to this API is
# cross-origin by design, not an edge case. Wide open here because this is
# meant for a private/local deployment; tighten to specific origins before
# exposing this beyond that.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
