"""FastAPI app. Start with:  uvicorn app.main:app --reload   (from the backend/ folder)"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db, errors
from app.config import ConfigError, get_settings
from app.routers import classify, gaps, health, pipeline, summary, vendors

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("dhaga.api")

try:
    settings = get_settings()
except ConfigError as exc:
    # Missing env var: refuse to start, and say which one.
    raise SystemExit(f"\nDhaga Returns can't start. {exc}\n") from None


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        with db.connect() as conn:
            stale = db.fail_stale_runs(conn)
        if stale:
            log.warning("Marked %s interrupted pipeline run(s) as failed", stale)
    except Exception:
        # The app still starts; /health reports the database as unreachable.
        log.exception("Could not reach the database at startup")
    yield


app = FastAPI(title="Dhaga & Co. Returns Insight", version="0.1.0", lifespan=lifespan)

errors.install(app)
# Added last so it is the outermost layer: error responses get CORS headers too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

for module in (health, pipeline, summary, vendors, gaps, classify):
    app.include_router(module.router)
