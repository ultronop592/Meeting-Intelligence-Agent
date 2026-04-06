import logging
import sys
import structlog
from core.config import settings

def setup_logging() -> None:
    """
    Configures logging for the application.
    Uses structlog for structured logging, with console output.
    """
    log_level = logging.DEBUG if settings.app_env == "development" else logging.INFO
    
    
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        
    )
    
    # // shared processors run on every log message
    
    shared_processors = [
        structlog.stdlib.add_log_level,              # Adds "level": "info"
        structlog.stdlib.add_logger_name,            # Adds "logger": "agents.transcription"
        structlog.processors.TimeStamper(fmt="iso"), # Adds "timestamp": "2026-03-22T10:00:00Z"
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,        # Formats exception tracebacks
    ]
    
    if settings.is_production:
        processors =  shared_processors + [structlog.processors.dict_tracebacks, structlog.processors.JSONRenderer()]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
 
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
 
 
def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger. Use at the top of each file:
        logger = get_logger(__name__)
    """
    return logging.getLogger(name)
        

