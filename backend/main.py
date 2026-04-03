"""ESG Reporting Platform — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routers import artifacts, assistants, runs, sources, threads

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB tables, storage, registry, agent service. Shutdown: close DB."""
    from backend.infra.db import close_db, get_session_factory, init_db
    from backend.infra.registry import init_registry
    from backend.infra.storage import LocalStorage
    from backend.services.agent import init_agent_service

    logger.info("Initialising database…")
    await init_db()

    storage = LocalStorage(settings.storage_root)
    init_registry(storage, get_session_factory())
    logger.info("Storage root: %s", settings.storage_root)

    init_agent_service()
    logger.info("Agent service ready.")

    yield

    await close_db()
    logger.info("Database connection closed.")


app = FastAPI(
    title="ESG Reporting Platform",
    version="0.1.0",
    description="Agent Protocol-compatible API for ESG compliance reporting.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assistants.router)
app.include_router(threads.router)
app.include_router(runs.router)
app.include_router(sources.router)
app.include_router(artifacts.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/info")
async def info():
    """Required by deep-agent-ui — called on startup to verify connection."""
    return {"default_assistant": "reporting-agent", "version": "0.1.0"}
