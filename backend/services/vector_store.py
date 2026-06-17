import os
import re
from typing import List, Tuple
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import text
import httpx

from backend.config import settings
from backend.models.database import RepairDocument

# ─────────────────────────────────────────────
# Cloud API Embedding Fetcher
# ─────────────────────────────────────────────

def _fetch_embedding_from_api(texts: List[str]) -> List[List[float]]:
    """
    Calls the Groq Cloud API to generate embeddings externally.
    This saves 400MB+ of server RAM by avoiding hosting local models.
    """
    api_key = os.environ.get("GROQ_API_KEY") or settings.groq_api_key
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is missing!")

    # Using Groq's high-speed, industry-standard embedding model
    url = "https://api.groq.com/openai/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "nomic-embed-text-v1.5",
        "input": texts
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            # Sort by index to maintain original document ordering
            results = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in results]
    except Exception as e:
        logger.error(f"Failed to fetch embeddings from Groq API: {e}")
        raise

# ─────────────────────────────────────────────
# Text Chunking
# ─────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap
    
    text = re.sub(r'\n{3,}', '\n\n', text.strip())
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            last_space = text.rfind(' ', start, end)
            if last_space > start:
                end = last_space
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        
    return chunks

# ─────────────────────────────────────────────
# Embedding Generation Adapters
# ─────────────────────────────────────────────

def get_embedding(text: str) -> List[float]:
    """Converts a single query string into a semantic vector via API."""
    cleaned_text = text.replace('\n', ' ').strip()
    if not cleaned_text:
        raise ValueError("Cannot embed empty text")
    
    embeddings = _fetch_embedding_from_api([cleaned_text])
    return embeddings[0]


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generates vectors for a list of strings efficiently in a single batch API call."""
    cleaned_texts = [t.replace('\n', ' ').strip() for t in texts if t.strip()]
    if not cleaned_texts:
        return []
        
    return _fetch_embedding_from_api(cleaned_texts)

# ─────────────────────────────────────────────
# Document Storage & Semantic Search (Preserved)
# ─────────────────────────────────────────────

def store_document_chunks(db: Session, source_file: str, content: str) -> int:
    logger.info(f"Processing document: {source_file}")
    chunks = chunk_text(content)
    logger.info(f"  Split into {len(chunks)} chunks")
    
    if not chunks:
        return 0
    
    try:
        embeddings = get_embeddings_batch(chunks)
    except Exception as e:
        logger.error(f"  Embedding batch pipeline execution failed: {e}")
        raise
    
    stored = 0
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        doc = RepairDocument(
            source_file=source_file,
            chunk_index=i,
            content=chunk,
            embedding=embedding
        )
        db.add(doc)
        stored += 1
    
    db.commit()
    logger.info(f"  ✅ Stored {stored} chunks from {source_file}")
    return stored


def search_similar_chunks(db: Session, query: str, top_k: int = 5) -> List[Tuple[str, str, float]]:
    if not query.strip():
        return []

    query_embedding = get_embedding(query)
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    sql = text(f"""
        SELECT source_file, content, (embedding <=> '{embedding_str}'::vector) AS distance
        FROM repair_documents
        ORDER BY embedding <=> '{embedding_str}'::vector
        LIMIT {top_k}
    """)

    try:
        result = db.execute(sql)
        rows = result.fetchall()
        return [(row.source_file, row.content, row.distance) for row in rows if row.distance < 1.0]
    except Exception as e:
        db.rollback()
        logger.error(f"Database semantic similarity operation failed: {e}")
        return []


def format_context_for_prompt(chunks: List[Tuple[str, str, float]]) -> str:
    if not chunks:
        return ""
    context_parts = []
    for source_file, content, distance in chunks:
        display_name = source_file.replace("_", " ").replace(".txt", "").title()
        context_parts.append(f"[From: {display_name}]\n{content}")
    return "\n\n---\n\n".join(context_parts)


def document_count(db: Session) -> int:
    return db.query(RepairDocument).count()


def clear_all_documents(db: Session) -> None:
    db.query(RepairDocument).delete()
    db.commit()
    logger.info("All documents cleared from vector store.")