"""
backend/models/database.py
---------------------------
Database connection setup + all table definitions.

CONCEPTS EXPLAINED:
- SQLAlchemy: Python ORM (Object Relational Mapper). Lets you write Python
  classes instead of raw SQL. Each class = one database table.
- Engine: The database connection pool. One engine per app.
- Session: A "unit of work" — you open a session, do queries, commit, close.
- Base: All models inherit from this. SQLAlchemy tracks them all.
"""

import uuid
import datetime
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector

from backend.config import settings

# ─────────────────────────────────────────────
# Engine & Session Factory
# ─────────────────────────────────────────────

engine = create_engine(
    settings.database_url,
    # pool_size: how many connections to keep open (reused across requests)
    pool_size=10,
    # max_overflow: extra connections allowed when pool is full
    max_overflow=20,
    # echo=True will print every SQL query — helpful for debugging
    echo=(settings.app_env == "development"),
)

SessionLocal = sessionmaker(
    autocommit=False,   # We control when to commit
    autoflush=False,    # We control when to flush to DB
    bind=engine
)

Base = declarative_base()


# ─────────────────────────────────────────────
# Database Models (Tables)
# ─────────────────────────────────────────────

class RepairDocument(Base):
    """
    Stores chunks of repair knowledge with their vector embeddings.
    This is what makes semantic search possible.

    Each row = one chunk of text + its 1536-dimensional vector embedding.
    The pgvector extension adds the `embedding` column type.
    """
    __tablename__ = "repair_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_file = Column(String(255), nullable=False)       # which file it came from
    chunk_index = Column(Integer, nullable=False)           # which chunk within the file
    content = Column(Text, nullable=False)                  # the actual text
    embedding = Column(Vector(384), nullable=True)         # OpenAI ada embedding (1536 dims)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<RepairDocument source={self.source_file} chunk={self.chunk_index}>"


class ChatSession(Base):
    """
    Represents a conversation session.
    Every time someone starts a new chat, a session is created.
    The session_id ties all messages together.
    """
    __tablename__ = "chat_sessions"

    id = Column(String(100), primary_key=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_active = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    # How many messages are in this session
    message_count = Column(Integer, default=0)

    def __repr__(self):
        return f"<ChatSession id={self.id} messages={self.message_count}>"


class ChatMessage(Base):
    """
    Individual messages within a session.
    role = "user" or "assistant"
    This is how the chatbot remembers conversation history.
    """
    __tablename__ = "chat_messages"

    id = Column(String(100), primary_key=True)
    session_id = Column(String(36), nullable=False, index=True)   # links to ChatSession
    role = Column(String(20), nullable=False)                     # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<ChatMessage role={self.role} session={self.session_id[:8]}...>"


class FeedbackRecord(Base):
    """
    Stores user feedback (thumbs up/down) on bot responses.
    This is how you improve the bot over time — real data on what works.
    """
    __tablename__ = "feedback_records"

    id = Column(String(100), primary_key=True)
    session_id = Column(String(36), nullable=False, index=True)
    message_id = Column(String(36), nullable=False)
    rating = Column(Integer, nullable=False)           # 1 = thumbs up, -1 = thumbs down
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ─────────────────────────────────────────────
# DB Initialization
# ─────────────────────────────────────────────

def init_db():
    """
    Creates all tables if they don't exist.
    Also enables the pgvector extension.
    Call this ONCE at startup.
    """
    from sqlalchemy import text
    with engine.connect() as conn:
        # Enable pgvector extension (must exist in PostgreSQL)
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    
    # Creates all tables defined above
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created/verified.")


def get_db():
    """
    FastAPI dependency — provides a DB session per request.
    The `finally` block ensures the session is ALWAYS closed,
    even if an exception occurs. This prevents connection leaks.
    
    Usage in a FastAPI route:
        def my_route(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
