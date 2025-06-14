"""
Production middleware and monitoring for Crawl4AI REST API.
"""
import os
import time
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pythonjsonlogger import jsonlogger
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import Request, Response, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

# Configure structured JSON logging
def setup_json_logging(log_level: str = "INFO"):
    """Configure JSON structured logging."""
    # Create logger
    logger = logging.getLogger()
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create JSON formatter
    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(levelname)s %(name)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Create stream handler with JSON formatter
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    return logger

# Configure Sentry error tracking
def setup_sentry(dsn: Optional[str] = None):
    """Initialize Sentry error tracking."""
    sentry_dsn = dsn or os.getenv("SENTRY_DSN")
    
    if sentry_dsn:
        sentry_logging = LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR
        )
        
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                sentry_logging
            ],
            traces_sample_rate=1.0,
            environment=os.getenv("RAILWAY_ENVIRONMENT", "development")
        )
        return True
    return False

# Configure rate limiting
def create_rate_limiter():
    """Create and configure rate limiter."""
    return Limiter(
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri=os.getenv("REDIS_URL", "memory://")
    )

# Prometheus metrics
REQUEST_COUNT = Counter(
    'crawl4ai_requests_total',
    'Total number of requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'crawl4ai_request_duration_seconds',
    'Request latency',
    ['method', 'endpoint']
)

CRAWL_COUNT = Counter(
    'crawl4ai_crawls_total',
    'Total number of pages crawled',
    ['crawl_type', 'status']
)

QUERY_COUNT = Counter(
    'crawl4ai_queries_total',
    'Total number of RAG queries',
    ['status']
)

ACTIVE_CRAWLS = Gauge(
    'crawl4ai_active_crawls',
    'Number of active crawl operations'
)

ERROR_COUNT = Counter(
    'crawl4ai_errors_total',
    'Total number of errors',
    ['error_type']
)

# Middleware for request logging and metrics
async def logging_middleware(request: Request, call_next):
    """Log all requests and collect metrics."""
    start_time = time.time()
    
    # Get request details
    request_id = request.headers.get("X-Request-ID", f"{time.time()}")
    
    # Log request
    logger = logging.getLogger(__name__)
    logger.info(
        "Request received",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_host": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("User-Agent", "unknown")
        }
    )
    
    # Process request
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Update metrics
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)
        
        # Log response
        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_seconds": duration
            }
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
        
    except Exception as e:
        duration = time.time() - start_time
        ERROR_COUNT.labels(error_type=type(e).__name__).inc()
        
        # Log error
        logger.error(
            "Request failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_seconds": duration
            },
            exc_info=True
        )
        
        # Re-raise the exception
        raise

# Advanced CORS configuration
def setup_advanced_cors(app):
    """Configure advanced CORS settings."""
    from fastapi.middleware.cors import CORSMiddleware
    
    # Get allowed origins from environment
    allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if not allowed_origins or allowed_origins == [""]:
        # Default allowed origins
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:8080",
            "http://localhost:5173",
            "https://*.railway.app",
            "https://*.vercel.app",
            "https://*.netlify.app"
        ]
    
    # Remove existing CORS middleware if any
    for i, middleware in enumerate(app.user_middleware):
        if middleware.cls == CORSMiddleware:
            app.user_middleware.pop(i)
            break
    
    # Add advanced CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
        allow_headers=[
            "Accept",
            "Accept-Language",
            "Content-Type",
            "Authorization",
            "X-Request-ID",
            "X-API-Key"
        ],
        expose_headers=[
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset"
        ],
        max_age=86400  # 24 hours
    )

# Metrics endpoint
async def metrics_endpoint(request: Request):
    """Prometheus metrics endpoint."""
    return PlainTextResponse(
        generate_latest(),
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )

# Custom error handlers
async def custom_404_handler(request: Request, exc: HTTPException):
    """Custom 404 error handler."""
    logger = logging.getLogger(__name__)
    logger.warning(
        "404 Not Found",
        extra={
            "path": request.url.path,
            "method": request.method,
            "client_host": request.client.host if request.client else "unknown"
        }
    )
    
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": f"The requested endpoint {request.url.path} does not exist",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

async def custom_500_handler(request: Request, exc: Exception):
    """Custom 500 error handler."""
    logger = logging.getLogger(__name__)
    logger.error(
        "Internal Server Error",
        extra={
            "path": request.url.path,
            "method": request.method,
            "error": str(exc),
            "error_type": type(exc).__name__
        },
        exc_info=True
    )
    
    # Send to Sentry if configured
    sentry_sdk.capture_exception(exc)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please try again later.",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# Initialize all production features
def init_production_features(app, logger=None):
    """Initialize all production features for the FastAPI app."""
    # Setup logging
    if logger is None:
        logger = setup_json_logging(os.getenv("LOG_LEVEL", "INFO"))
    
    # Setup Sentry
    sentry_enabled = setup_sentry()
    if sentry_enabled:
        logger.info("Sentry error tracking initialized")
    
    # Setup rate limiting
    limiter = create_rate_limiter()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # Add middleware
    @app.middleware("http")
    async def add_logging_middleware(request: Request, call_next):
        return await logging_middleware(request, call_next)
    
    # Setup advanced CORS
    setup_advanced_cors(app)
    
    # Add metrics endpoint
    app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)
    
    # Add custom error handlers
    app.add_exception_handler(404, custom_404_handler)
    app.add_exception_handler(500, custom_500_handler)
    
    logger.info("Production features initialized successfully")
    
    return {
        "logger": logger,
        "limiter": limiter,
        "sentry_enabled": sentry_enabled
    }