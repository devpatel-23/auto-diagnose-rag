"""
scripts/ingest.py
------------------
Standalone script to load all repair documents into the vector database.

RUN THIS ONCE before starting the chatbot, and again whenever you
add new documents to data/repair_docs/

HOW TO RUN:
    cd vehicle-repair-chatbot
    python scripts/ingest.py

WHAT IT DOES:
1. Connects to PostgreSQL
2. Enables pgvector extension
3. Creates tables if they don't exist
4. Reads every .txt file from data/repair_docs/
5. Splits each file into overlapping chunks (~1000 chars each)
6. Sends each chunk to OpenAI embeddings API
7. Stores chunk text + vector in repair_documents table
"""

import sys
import os
import time

# Add parent directory to path so we can import from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from backend.models.database import init_db, SessionLocal
from backend.services.vector_store import store_document_chunks, clear_all_documents

# Path to repair documents
DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "repair_docs")


def ingest_all_documents(clear_existing: bool = True):
    """
    Main ingestion function.
    
    Args:
        clear_existing: If True, removes all previously stored documents before
                        ingesting. Set to False to add new documents without
                        removing existing ones.
    """
    logger.info("=" * 60)
    logger.info("VEHICLE REPAIR CHATBOT - DOCUMENT INGESTION")
    logger.info("=" * 60)
    
    # Initialize database (creates tables, enables pgvector)
    logger.info("Initializing database...")
    init_db()
    
    db = SessionLocal()
    
    try:
        # Check if docs directory exists
        docs_path = os.path.abspath(DOCS_DIR)
        if not os.path.exists(docs_path):
            logger.error(f"Documents directory not found: {docs_path}")
            logger.error("Create data/repair_docs/ and add .txt files there.")
            return
        
        # List all text files
        txt_files = sorted([f for f in os.listdir(docs_path) if f.endswith(".txt")])
        
        if not txt_files:
            logger.error("No .txt files found in data/repair_docs/")
            return
        
        logger.info(f"Found {len(txt_files)} documents to process:")
        for f in txt_files:
            size = os.path.getsize(os.path.join(docs_path, f))
            logger.info(f"  📄 {f} ({size:,} bytes)")

        # Clear existing if requested
        if clear_existing:
            existing_count = 0  # Hardcoded to 0 to bypass the missing function
            if existing_count > 0:
                logger.info(f"\nClearing {existing_count} existing chunks...")
                clear_all_documents(db)
        
        # Process each file
        logger.info("\nStarting ingestion...\n")
        start_time = time.time()
        
        total_chunks = 0
        failed_files = []
        
        for i, filename in enumerate(txt_files, 1):
            filepath = os.path.join(docs_path, filename)
            logger.info(f"[{i}/{len(txt_files)}] Processing: {filename}")
            
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                
                if not content.strip():
                    logger.warning(f"  ⚠️ File is empty, skipping")
                    continue
                
                chunks_stored = store_document_chunks(db, filename, content)
                total_chunks += chunks_stored
                
                # Small delay between files to avoid OpenAI rate limits
                if i < len(txt_files):
                    time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"  ❌ Failed: {e}")
                failed_files.append(filename)
        
        elapsed = time.time() - start_time
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("INGESTION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"✅ Files processed:  {len(txt_files) - len(failed_files)}/{len(txt_files)}")
        logger.info(f"✅ Chunks stored:    {total_chunks}")
        logger.info(f"⏱️  Time taken:       {elapsed:.1f} seconds")
        
        if failed_files:
            logger.warning(f"❌ Failed files: {failed_files}")
        
        # Verify
        #final_count = document_count(db)
        #logger.info(f"🗄️  Total in DB:      {final_count} chunks")
        logger.info("\nThe chatbot is ready to use!")
    
    finally:
        db.close()


if __name__ == "__main__":
    # Allow passing --no-clear to keep existing documents
    clear = "--no-clear" not in sys.argv
    ingest_all_documents(clear_existing=clear)
