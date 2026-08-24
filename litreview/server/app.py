"""FastAPI application factory: /api + the static frontend at /."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .jobs import JobRunner
from .routes import router
from .sse import EventBus
from .store import SurveyStore

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def create_app(data_dir: str | Path = "var") -> FastAPI:
    app = FastAPI(title="LitReview", docs_url="/api/docs", openapi_url="/api/openapi.json")
    store = SurveyStore(data_dir)
    bus = EventBus()
    app.state.store = store
    app.state.bus = bus
    app.state.jobs = JobRunner(store, bus)
    app.include_router(router, prefix="/api")
    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True),
                  name="frontend")
    return app
