"""
FastAPI main application
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from app.api import workflows, broker, portfolio

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Workflow Execution Backend...")
    logger.info(f"Python version: {os.sys.version}")
    logger.info(f"Environment: {os.getenv('ENV', 'development')}")
    
    # Initialize database - create all tables
    from app.storage import init_db
    from app.storage.models import (
        ExecutionModel,
        ExecutionLogModel,
        OrderModel,
        PositionModel,
        BrokerSessionModel
    )
    init_db()
    logger.info("Database initialized - all tables created")
    
    # Initialize services
    from app.services.market_data import market_data_service
    from app.services.workflow_engine import workflow_engine
    
    logger.info(f"Market data service initialized with {market_data_service.cache.ttl_seconds}s cache TTL")
    logger.info(f"Workflow engine initialized with {len(workflow_engine.node_executors)} executors")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Workflow Execution Backend...")
    # Clean up resources if needed
    market_data_service.cache.clear()
    logger.info("Cleanup completed")


# Create FastAPI app
app = FastAPI(
    title="Workflow Execution Backend",
    description="Python FastAPI backend for executing trading workflows with real-time market data",
    version="1.0.0",
    lifespan=lifespan
)


# Configure CORS
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:9002,http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info(f"CORS enabled for origins: {cors_origins}")


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all uncaught exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "path": str(request.url)
        }
    )


# Include routers
app.include_router(workflows.router)
app.include_router(broker.router)
app.include_router(portfolio.router)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Workflow Execution Backend",
        "version": "1.0.0",
        "description": "Python FastAPI backend for executing trading workflows",
        "status": "running",
        "docs": "/docs",
        "health": "/api/workflows/health"
    }


# Additional health check at root level
@app.get("/health")
async def health():
    """Simple health check"""
    return {
        "status": "healthy",
        "service": "workflow-execution-backend"
    }


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting server on {host}:{port}")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=True,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )

