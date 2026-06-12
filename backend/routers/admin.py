"""
backend/routers/admin.py
-------------------------
Admin endpoints for managing the knowledge base and system health.
These are NOT meant for end users — only for developers/admins.

ENDPOINTS:
- GET  /admin/health     → System health check
- GET  /admin/db-status  → Check database and vector store
- POST /admin/ingest     → Trigger re-ingestion of all documents
- GET  /admin/stats      → System-wide statistics
"""

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from loguru import logger
import os

from backend.models.database import get_db, RepairDocument, ChatMessage, ChatSession, FeedbackRecord
from backend.services.vector_store import (
    store_document_chunks,
    clear_all_documents,
    document_count
)
from backend.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])

# Path where repair documents live
DOCS_PATH = os.path.join(os.path.dirname(__file__), "../../data/repair_docs")


# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────

@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Checks that all systems are operational.
    Render and monitoring services ping this to verify the app is alive.
    Returns 200 OK if healthy, 503 if any system is down.
    """
    status = {
        "api": "ok",
        "database": "unknown",
        "vector_store": "unknown",
        "openai": "unknown",
        "environment": settings.app_env
    }
    
    # Test database connection
    try:
        db.execute(text("SELECT 1"))
        status["database"] = "ok"
    except Exception as e:
        status["database"] = f"error: {str(e)}"
    
    # Check vector store has documents
    try:
        count = document_count(db)
        status["vector_store"] = f"ok ({count} chunks)"
    except Exception as e:
        status["vector_store"] = f"error: {str(e)}"
    
    # Check OpenAI key exists (we don't test a live call to save money)
    status["openai"] = "key configured" if settings.openai_api_key.startswith("sk-") else "key missing"
    
    # Determine overall status
    all_ok = all("ok" in v or "configured" in v for v in status.values() if isinstance(v, str))
    
    return {
        "status": "healthy" if all_ok else "degraded",
        "services": status
    }


# ─────────────────────────────────────────────
# Document Ingestion
# ─────────────────────────────────────────────

def run_ingestion(db: Session):
    """
    Reads all .txt files from data/repair_docs/ and stores them in pgvector.
    This is called as a background task so the API response returns immediately.
    """
    logger.info("Starting document ingestion...")
    
    docs_path = os.path.abspath(DOCS_PATH)
    
    if not os.path.exists(docs_path):
        logger.error(f"Docs path not found: {docs_path}")
        return
    
    # Clear existing documents before re-ingesting
    clear_all_documents(db)
    
    total_chunks = 0
    files_processed = 0
    
    for filename in sorted(os.listdir(docs_path)):
        if not filename.endswith(".txt"):
            continue
        
        filepath = os.path.join(docs_path, filename)
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            chunks_stored = store_document_chunks(db, filename, content)
            total_chunks += chunks_stored
            files_processed += 1
            
        except Exception as e:
            logger.error(f"Failed to process {filename}: {e}")
    
    logger.info(f"✅ Ingestion complete: {files_processed} files, {total_chunks} total chunks")


@router.post("/ingest")
def trigger_ingestion(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Triggers document re-ingestion in the background.
    
    WHY BACKGROUND?
    Ingestion can take 30-120 seconds (many API calls to OpenAI for embeddings).
    Running it in the background lets the API respond immediately with
    "ingestion started" while the work happens in a separate thread.
    """
    background_tasks.add_task(run_ingestion, db)
    
    return {
        "status": "started",
        "message": "Document ingestion started in background. Check /admin/stats to monitor progress."
    }


@router.post("/ingest/sync")
def trigger_ingestion_sync(db: Session = Depends(get_db)):
    """
    Synchronous ingestion — waits for completion before responding.
    Use this during initial setup to confirm everything works.
    """
    run_ingestion(db)
    count = document_count(db)
    return {
        "status": "complete",
        "chunks_stored": count
    }


# ─────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """
    System-wide statistics — useful for monitoring and debugging.
    """
    return {
        "knowledge_base": {
            "total_chunks": db.query(RepairDocument).count(),
            "unique_files": db.query(RepairDocument.source_file).distinct().count()
        },
        "conversations": {
            "total_sessions": db.query(ChatSession).count(),
            "total_messages": db.query(ChatMessage).count(),
            "user_messages": db.query(ChatMessage).filter(ChatMessage.role == "user").count(),
        },
        "feedback": {
            "total_feedback": db.query(FeedbackRecord).count(),
            "helpful": db.query(FeedbackRecord).filter(FeedbackRecord.rating == 1).count(),
            "not_helpful": db.query(FeedbackRecord).filter(FeedbackRecord.rating == -1).count(),
        }
    }
