"""
scripts/setup_db.py
--------------------
One-time setup script. Run this BEFORE running ingest.py

This does:
1. Connects to your PostgreSQL database
2. Enables the pgvector extension  
3. Creates all required tables

RUN WITH:
    python scripts/setup_db.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from sqlalchemy import text
from backend.models.database import engine, init_db, Base
from backend.config import settings


def setup():
    logger.info("=" * 50)
    logger.info("DATABASE SETUP")
    logger.info("=" * 50)
    logger.info(f"Connecting to: {settings.database_url[:50]}...")
    
    try:
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            logger.info(f"✅ Connected to PostgreSQL: {version[:50]}")
        
        # Initialize (enables pgvector + creates tables)
        init_db()
        
        # Verify tables were created
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]
        
        logger.info(f"\n✅ Tables created: {tables}")
        logger.info("\n🎉 Database setup complete!")
        logger.info("\nNext step: Run python scripts/ingest.py")
    
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}")
        logger.error("\nTroubleshooting:")
        logger.error("1. Is PostgreSQL running?")
        logger.error("2. Is the DATABASE_URL in your .env correct?")
        logger.error("3. Does the database exist? (CREATE DATABASE vehicle_repair_bot;)")
        logger.error("4. Is pgvector extension available? (needs PostgreSQL 14+ and pgvector installed)")
        sys.exit(1)


if __name__ == "__main__":
    setup()
