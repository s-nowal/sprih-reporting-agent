"""ESG Reporting Platform — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routers import (
    files,
    google_auth,
    runs,
    sources,
    threads,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, storage, registry, checkpointer, agent service. Shutdown: close all."""
    from contextlib import AsyncExitStack

    from langgraph.checkpoint.mysql.aio import AIOMySQLSaver

    from backend.infra.db import get_checkpointer_url
    from backend.infra.registry import Registry, set_registry, teardown_registry
    from backend.services.agent import init_agent_service

    logger.info("Initialising infrastructure…")
    registry = await Registry.from_config(settings)
    set_registry(registry)

    # --- Durable LangGraph checkpointer (MariaDB) -------------------------------
    # Persists conversation history (thread state) in the same MariaDB instance
    # used for application data so backups, schema lifecycle, and connection
    # management all live in one place. ``AIOMySQLSaver.from_conn_string``
    # returns an async context manager that owns its aiomysql pool; binding it
    # to ``AsyncExitStack`` ties the pool's lifetime to the FastAPI lifespan.
    async with AsyncExitStack() as stack:
        checkpointer = await stack.enter_async_context(
            AIOMySQLSaver.from_conn_string(get_checkpointer_url())
        )
        await checkpointer.setup()
        logger.info(
            "Checkpointer ready (MariaDB %s/%s)",
            settings.db_host,
            settings.db_name,
        )

        init_agent_service(checkpointer)
        logger.info("Agent service ready.")

        yield

        await teardown_registry()
        logger.info("Infrastructure torn down.")


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

app.include_router(threads.router)
app.include_router(runs.router)
app.include_router(sources.router)
app.include_router(files.router)
app.include_router(google_auth.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/info")
async def info():
    """Required by deep-agent-ui — called on startup to verify connection."""
    return {"default_assistant": "reporting-agent", "version": "0.1.0"}
