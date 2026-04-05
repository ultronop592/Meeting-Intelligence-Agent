import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from Backend.api.routes import router
from Backend.core.config import settings
from Backend.core.logging import setup_logging
from Backend.db.database import init_db
from Backend.models.schemas import HealthResponse

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    logger.info("Environment: %s", settings.app_env)
    try:
        await init_db()
        logger.info("Database initialized successfully")
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
    logger.exception("Unhandled exception during request %s %s", request.method, request.url.path)
    detail = str(exc) if not settings.is_production else "Internal Server Error"
    return JSONResponse(status_code=500, content={"detail": detail, "path": str(request.url.path)})


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



