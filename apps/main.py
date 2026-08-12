"""
FastAPI main application for HubSpot Master Service.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apps.config import settings
from apps.models.base import init_db

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting HubSpot Master Service")
    logger.info(f"Environment: {settings.app_env}")
    
    # Initialize database
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down HubSpot Master Service")


# Create FastAPI application
app = FastAPI(
    title="HubSpot Master Service",
    description="Extract, normalize, and publish HubSpot CRM data",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "hubspot-master-service",
        "environment": settings.app_env,
    }


# Stats endpoint
@app.get("/api/stats")
async def get_stats():
    """Get service statistics."""
    return {
        "service": "hubspot-master-service",
        "version": "1.0.0",
        "environment": settings.app_env,
    }


# Import and register routers
from apps.api import scan, credentials, maintenance, audit, normalization

app.include_router(scan.router, prefix="/api/scan", tags=["scan"])
app.include_router(normalization.router, prefix="/api/normalization", tags=["normalization"])
app.include_router(credentials.router, prefix="/api", tags=["credentials"])
app.include_router(maintenance.router, prefix="/api/maintenance", tags=["maintenance"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "apps.main:app",
        host="0.0.0.0",
        port=3000,
        reload=settings.app_env == "development",
    )
