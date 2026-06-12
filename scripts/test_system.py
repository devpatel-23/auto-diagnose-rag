"""
scripts/test_system.py
-----------------------
Comprehensive test of the entire system.
Run this after setup to verify everything is working before using the chatbot.

RUN WITH:
    python scripts/test_system.py
"""

import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger


def test_config():
    """Tests that all environment variables are loaded."""
    logger.info("\n[1/5] Testing configuration...")
    
    from backend.config import settings
    
    assert settings.openai_api_key.startswith("sk-"), \
        "OPENAI_API_KEY not set or invalid format"
    assert settings.database_url.startswith("postgresql"), \
        "DATABASE_URL not set or invalid format"
    
    logger.info(f"  ✅ OpenAI key: {settings.openai_api_key[:12]}...")
    logger.info(f"  ✅ Database: {settings.database_url[:40]}...")
    logger.info(f"  ✅ Model: {settings.openai_model}")


def test_database():
    """Tests database connection and tables."""
    logger.info("\n[2/5] Testing database connection...")
    
    from sqlalchemy import text
    from backend.models.database import engine, SessionLocal, RepairDocument, ChatMessage
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM repair_documents"))
        count = result.fetchone()[0]
        logger.info(f"  ✅ Database connected")
        logger.info(f"  ✅ repair_documents table: {count} rows")
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM chat_messages"))
        count = result.fetchone()[0]
        logger.info(f"  ✅ chat_messages table: {count} rows")


def test_embeddings():
    """Tests OpenAI embedding API."""
    logger.info("\n[3/5] Testing embeddings...")
    
    from backend.services.vector_store import get_embedding
    
    test_text = "How do I change brake pads?"
    embedding = get_embedding(test_text)
    
    assert len(embedding) == 1536, f"Expected 1536 dimensions, got {len(embedding)}"
    assert all(isinstance(v, float) for v in embedding[:5]), "Expected floats"
    
    logger.info(f"  ✅ Embedding generated: {len(embedding)} dimensions")
    logger.info(f"  ✅ First 3 values: {embedding[:3]}")


def test_vector_search():
    """Tests similarity search."""
    logger.info("\n[4/5] Testing vector search...")
    
    from backend.models.database import SessionLocal
    from backend.services.vector_store import search_similar_chunks, document_count
    
    db = SessionLocal()
    try:
        count = document_count(db)
        
        if count == 0:
            logger.warning("  ⚠️ No documents in vector store. Run ingest.py first.")
            return
        
        results = search_similar_chunks(db, "brake pads worn squeaking", top_k=3)
        
        assert len(results) > 0, "No results returned from vector search"
        
        logger.info(f"  ✅ Vector store: {count} chunks")
        logger.info(f"  ✅ Search returned {len(results)} results")
        logger.info(f"  ✅ Best match distance: {results[0][2]:.4f}")
        logger.info(f"  ✅ Source: {results[0][0]}")
        logger.info(f"  ✅ Preview: {results[0][1][:100]}...")
    finally:
        db.close()


async def test_chat():
    """Tests the full chat pipeline."""
    logger.info("\n[5/5] Testing chat pipeline...")
    
    from backend.models.database import SessionLocal
    from backend.services.chat_service import chat_simple
    import uuid
    
    db = SessionLocal()
    try:
        session_id = str(uuid.uuid4())
        
        response = await chat_simple(
            db,
            "What are the symptoms of a failing water pump?",
            session_id
        )
        
        assert len(response) > 50, "Response too short"
        assert "water pump" in response.lower() or "coolant" in response.lower(), \
            "Response doesn't seem relevant"
        
        logger.info(f"  ✅ Chat response received ({len(response)} chars)")
        logger.info(f"  ✅ Preview: {response[:150]}...")
    finally:
        db.close()


async def run_all_tests():
    """Run all tests in sequence."""
    logger.info("=" * 60)
    logger.info("VEHICLE REPAIR CHATBOT — SYSTEM TEST")
    logger.info("=" * 60)
    
    tests = [
        ("Configuration", test_config, False),
        ("Database", test_database, False),
        ("Embeddings", test_embeddings, False),
        ("Vector Search", test_vector_search, False),
        ("Chat Pipeline", test_chat, True),   # True = async
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn, is_async in tests:
        try:
            if is_async:
                await test_fn()
            else:
                test_fn()
            passed += 1
        except AssertionError as e:
            logger.error(f"  ❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            logger.error(f"  ❌ ERROR: {e}")
            failed += 1
    
    logger.info("\n" + "=" * 60)
    logger.info(f"RESULTS: {passed} passed, {failed} failed")
    logger.info("=" * 60)
    
    if failed == 0:
        logger.info("🎉 All tests passed! The chatbot is ready.")
    else:
        logger.error("❌ Some tests failed. Check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
