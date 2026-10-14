"""AegisOps FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from observability.tracer import init_tracer
from observability.middleware import ObservabilityMiddleware
from observability.metrics import init_metrics

settings = get_settings()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aegisops")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AegisOps",
    description=(
        "AI-native, multi-agent enterprise incident investigation and remediation platform. "
        "Combines RAG, specialized agents, guardrails, human approval, and full observability."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Observability — traces every request with an OTel span
app.add_middleware(ObservabilityMiddleware)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from api.incidents import router as incidents_router  # noqa: E402

app.include_router(incidents_router)

# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def on_startup() -> None:
    """Initialize database tables, OTel tracer, and metrics on startup."""
    logger.info("AegisOps starting up...")

    # Initialise observability (no-op if collector is not reachable)
    try:
        init_tracer()
        init_metrics()
        logger.info("OpenTelemetry tracer and metrics initialized.")
    except Exception as exc:
        logger.warning(f"Observability init failed (non-fatal): {exc}")

    if settings.app_env == "development":
        try:
            from models.database import create_tables
            create_tables()
            logger.info("Database tables created/verified.")
        except Exception as exc:
            logger.warning(f"Could not connect to database at startup: {exc}")
    logger.info("AegisOps ready.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("AegisOps shutting down.")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """Basic liveness check."""
    return {"status": "ok", "service": "aegisops-api", "version": "0.1.0"}


@app.get("/", tags=["system"])
async def root() -> dict:
    return {"message": "AegisOps API — see /docs for API reference"}
