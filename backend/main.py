"""ESG Reporting Platform — FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routers import artifacts, assistants, runs, sources, threads

app = FastAPI(
    title="ESG Reporting Platform",
    version="0.1.0",
    description="Agent Protocol-compatible API for ESG compliance reporting.",
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
