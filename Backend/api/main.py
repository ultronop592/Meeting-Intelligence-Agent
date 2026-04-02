import time
import logging 
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from Backend.api.routes import router
from Backend.core.config import settings
from Backend.core.logging import setup_logging 
from Backend.db.database import init_db
from Backend.api.routes import router
from Backend.models.schemas import HealthResponse

setup_logging()
logger = logging.getLogger(__name__)


# lifeSpan 

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Meeting Intelligence Ageny v%s", settings.app_version)
    logger.info("Environment: %s", settings.app_env)
    
    
    
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        
        
        
    import os 
    os.makedirs(settings.upload_dir, exist_ok=True)
    logger.info("Upload directory ensured at: %s", settings.upload_dir)
    logger.info("Application startup completed - ready to process meetings")
    yield
    
    logger.info("Shutting down Meeting Intelligence Ageny")
    
    
    # FASTAPI APP
    
    app = FastAPI(
        title = settings.app_name,
        description =(
            "Agentic AI system that processes meeting recordings using LangGraph. "
            "Transcribes audio, extracts action items and decisions, generates summaries, "
            "and integrates with Jira, Google Calendar, Slack, and email."
        ),
        version= settings.app_version,
        lifespan=lifespan
        
        
        docs_url = "/docs" if not settings.is_production else None,
        redoc_url = "/redoc" if not settings.is_production else None,
    )
    


# CORS MIDDLEWARE

ALLOWED_ORIGINS =[
    "http://localhost:3000",        # Next.js dev server
    "http://localhost:3001",        # Next.js alt port
    "http://127.0.0.1:3000",
]

if hasattr(settings, "frontend_url") and settings.frontend_url:
    ALLOWED_ORIGINS.append(settings.frontend_url)
    
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    
)
    
    
# GZIP MIDDLEWARE

app.add_middleware(GZipMiddleware, minimum_size=1000)

# REQUESTS LOAGGING MIDDLEWARE

@app.middleware("http")
async def log_requests(request:Request, call_next):
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = round((time.time() - start_time) * 1000)
    
    logger.info(
        "HTTP %s %s → %d (%dms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
 
    return response
        
# global exception handler

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception during request: %s %s - %s",
        request.method,
        request.url.path,
        exc,    
    )
    
    details = str(rxc) if not settings.is_production else "Internal Server Error"
    
    return JSONResponse(
        status_code=500,
        content={"detail": details, "path": str(request.url.path)},
    )
    

# Register API routes

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    return HealthResponse(status="ok", version=settings.app_version)



@app.get("/", tags =["health"])

async def root():
    return {
           "message": "Meeting Intelligence Agent API",
        "version": settings.app_version,
        "docs":    "/docs" if not settings.is_production else "disabled in production",
    }

    }


