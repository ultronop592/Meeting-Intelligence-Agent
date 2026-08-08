import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.auth_routes import auth_router
from api.routes import router
from core.config import settings
from core.logging import setup_logging
from db.database import init_db, recover_stale_jobs
from models.schemas import HealthResponse

setup_logging()
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    logger.info("Environment: %s", settings.app_env)
    
    sentry_dsn = getattr(settings, "sentry_dsn", None) or os.getenv("SENTRY_DSN")
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=settings.app_env,
                traces_sample_rate=1.0,
                integrations=[FastApiIntegration()],
            )
            logger.info("Sentry monitoring initialized successfully")
        except Exception as sentry_exc:
            logger.warning("Sentry initialization skipped or failed: %s", sentry_exc)

    try:
        await init_db()
        logger.info("Database initialized successfully")
        recovered = await recover_stale_jobs()
        if recovered:
            logger.warning("%d orphaned processing job(s) marked as failed on startup", recovered)
    except Exception as exc:
        logger.error("Failed to initialize database: %s", exc)

    os.makedirs(settings.upload_dir, exist_ok=True)
    logger.info("Upload directory ensured at: %s", settings.upload_dir)
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="Meeting Intelligence Agent API",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000)
    logger.info(
        "HTTP %s %s -> %d (%dms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, RateLimitExceeded):
        return _rate_limit_exceeded_handler(request, exc)
    logger.exception("Unhandled exception during request %s %s", request.method, request.url.path)
    detail = str(exc) if not settings.is_production else "Internal Server Error"
    return JSONResponse(status_code=500, content={"detail": detail, "path": str(request.url.path)})


app.include_router(auth_router)
app.include_router(router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    return HealthResponse(status="ok", version=settings.app_version, database="neon")


@app.get("/", tags=["health"])
async def root():
    return {
        "message": "Meeting Intelligence Agent API",
        "version": settings.app_version,
        "docs": "/docs" if not settings.is_production else "disabled in production",
    }



