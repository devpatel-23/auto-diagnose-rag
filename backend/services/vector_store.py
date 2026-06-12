"""
backend/services/vector_store.py
---------------------------------
Handles all vector embedding and semantic search operations.

CONCEPTS EXPLAINED:
- Embedding: Converting text into a list of numbers (vector) that captures meaning.
  Similar texts produce similar vectors. "brake noise" and "squealing brakes"
  will be close together in vector space even though the words differ.
- Cosine similarity: How we measure closeness between vectors (angle between them).
- pgvector: PostgreSQL extension that stores vectors and lets us do similarity search.
- Chunking: We can't embed entire documents at once (too long). We split them
  into overlapping chunks so no context is lost at boundaries.
"""

import os
import re
from typing import List, Tuple
from loguru import logger
from langchain_huggingface import HuggingFaceEmbeddings
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.config import settings
from backend.models.database import RepairDocument

# Initialize OpenAI client once
embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# ─────────────────────────────────────────────
# Text Chunking
# ─────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
    """
    Splits a long document into overlapping chunks.
    
    WHY OVERLAP?
    If a repair procedure spans the boundary of two chunks, we'd lose context.
    Overlap ensures each chunk has context from the previous one.
    
    Example with chunk_size=20, overlap=5:
    Text:    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    Chunk 1: "ABCDEFGHIJKLMNOPQRST"
    Chunk 2: "NOPQRSTUVWXYZ"        (starts 5 chars before end of chunk 1)
    """
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap
    
    # Clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text.strip())
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Don't cut in the middle of a word — find last space before end
        if end < len(text):
            last_space = text.rfind(' ', start, end)
            if last_space > start:
                end = last_space
        
        chunk = text[start:end].strip()
        if chunk:  # Don't add empty chunks
            chunks.append(chunk)
        
        # Move start forward, but overlap with previous chunk
        start = end - overlap
    
    return chunks


# ─────────────────────────────────────────────
# Embedding Generation
# ─────────────────────────────────────────────

def get_embedding(text: str) -> List[float]:
    """
    Converts text into a vector using the local HuggingFace embedding model.

    Returns a list of 384 floats (for all-MiniLM-L6-v2).
    The vector is what gets stored in pgvector and used for similarity search.
    """
    # Clean text — remove excessive whitespace
    text = text.replace('\n', ' ').strip()

    if not text:
        raise ValueError("Cannot embed empty text")

    # embed_query is LangChain's method for single texts
    return embedding_model.embed_query(text)


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Embeds multiple texts locally in one batch.
    Much faster than calling get_embedding() in a loop.
    """
    texts = [t.replace('\n', ' ').strip() for t in texts if t.strip()]

    # embed_documents automatically handles lists of text
    return embedding_model.embed_documents(texts)


# ─────────────────────────────────────────────
# Document Storage
# ─────────────────────────────────────────────

def store_document_chunks(
    db: Session,
    source_file: str,
    content: str
) -> int:
    """
    Full pipeline: text → chunks → embeddings → database.
    
    Returns the number of chunks stored.
    """
    logger.info(f"Processing document: {source_file}")
    
    # Step 1: Split into chunks
    chunks = chunk_text(content)
    logger.info(f"  Split into {len(chunks)} chunks")
    
    if not chunks:
        logger.warning(f"  No chunks generated from {source_file}")
        return 0
    
    # Step 2: Get embeddings for all chunks in one batch call
    try:
        embeddings = get_embeddings_batch(chunks)
    except Exception as e:
        logger.error(f"  Embedding failed: {e}")
        raise
    
    # Step 3: Store each chunk with its embedding
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


# ─────────────────────────────────────────────
# Semantic Search
# ─────────────────────────────────────────────

def search_similar_chunks(
    db: Session,
    query: str,
    top_k: int = 5
) -> List[Tuple[str, str, float]]:
    if not query.strip():
        return []

    query_embedding = get_embedding(query)
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    from sqlalchemy import text
    sql = text(f"""
        SELECT
            source_file,
            content,
            (embedding <=> '{embedding_str}'::vector) AS distance
        FROM repair_documents
        ORDER BY embedding <=> '{embedding_str}'::vector
        LIMIT {top_k}
    """)

    try:
        result = db.execute(sql)
        rows = result.fetchall()
        return [
            (row.source_file, row.content, row.distance)
            for row in rows
            if row.distance < 1.0
        ]
    except Exception as e:
        db.rollback()
        return []


def format_context_for_prompt(
    chunks: List[Tuple[str, str, float]]
) -> str:
    """
    Takes raw search results and formats them into a readable context
    block that gets injected into the LLM prompt.
    
    Example output:
    [Source: engine_diagnostics.txt]
    Brake pad replacement: Check pad thickness...
    
    [Source: brakes_suspension.txt]
    ABS system: If ABS light comes on...
    """
    if not chunks:
        return ""
    
    context_parts = []
    for source_file, content, distance in chunks:
        # Clean up the source filename for display
        display_name = source_file.replace("_", " ").replace(".txt", "").title()
        context_parts.append(f"[From: {display_name}]\n{content}")
    
    return "\n\n---\n\n".join(context_parts)


def document_count(db: Session) -> int:
    """Returns the total number of document chunks stored."""
    return db.query(RepairDocument).count()


def clear_all_documents(db: Session) -> None:
    """Deletes all stored documents. Used for re-ingestion."""
    db.query(RepairDocument).delete()
    db.commit()
    logger.info("All documents cleared from vector store.")
