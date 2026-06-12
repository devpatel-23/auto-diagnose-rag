"""
backend/main.py
----------------
The FastAPI application entry point.

THIS FILE:
1. Creates the FastAPI app instance
2. Configures CORS (Cross-Origin Resource Sharing)
3. Includes all routers
4. Initializes the database on startup
5. Starts the server when run directly

HOW FASTAPI WORKS:
FastAPI is a modern Python web framework built on top of Starlette (async) and Pydantic (validation).
- Routes are defined with decorators (@app.get, @app.post, etc.)
- Request/response schemas are Pydantic models (automatic validation)
- Async support allows handling many concurrent requests without blocking
- Auto-generates API documentation at /docs (Swagger UI)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import sys

from backend.config import settings
from backend.models.database import init_db
from backend.routers import chat, admin


# ─────────────────────────────────────────────
# Logging Setup
# ─────────────────────────────────────────────

# Configure loguru for better log formatting
logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
    level="INFO" if settings.app_env == "production" else "DEBUG"
)


# ─────────────────────────────────────────────
# Application Lifecycle
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code that runs at startup and shutdown.
    
    @asynccontextmanager with `yield` splits it into:
    - Everything BEFORE yield: runs at startup
    - Everything AFTER yield: runs at shutdown
    
    This is the modern FastAPI way (replaces @app.on_event("startup"))
    """
    # ── STARTUP ──────────────────────────────
    logger.info("Starting Vehicle Repair Chatbot API...")
    logger.info(f"   Environment: {settings.app_env}")
    logger.info("   Model: Groq (llama-3.3-70b-versatile)")
    
    # Initialize database tables
    init_db()
    
    logger.info("API ready!")
    
    yield
    
    # ── SHUTDOWN
    logger.info("Shutting down...")


# FastAPI App Instance


app = FastAPI(
    title="Vehicle Repair & Restoration Chatbot API",
    description="""
    AI-powered assistant for vehicle repair, diagnostics, and restoration.
    
    ## Features
    - RAG-powered answers from comprehensive repair knowledge base
    - OBD-II fault code lookup and diagnosis
    - Restoration guidance for classic vehicles
    - Maintenance schedule recommendations
    - Persistent conversation history
    """,
    version="1.0.0",
    lifespan=lifespan,
    # Disable docs in production for security
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

# Middleware

# CORS — allows the Chainlit frontend (different port) to call this API
# In production, replace "*" with your actual domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "development" else [
        "https://your-chainlit-app.onrender.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip — compresses responses over 1KB (faster transfer)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include Routers

app.include_router(chat.router)
app.include_router(admin.router)

# Root Endpoint

@app.get("/")
def root():
    return {
        "name": "Vehicle Repair Chatbot API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }

# Run Directly (Development)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Auto-restart on code changes during development
        log_level="info"
    )
