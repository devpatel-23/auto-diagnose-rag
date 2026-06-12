"""
backend/models/__init__.py
----------------------------
Makes `models` a Python package and exports key database objects
so the rest of the app can do:
    from backend.models import get_db, ChatMessage
instead of the longer:
    from backend.models.database import get_db, ChatMessage
"""
from backend.models.database import (
    Base,
    engine,
    SessionLocal,
    get_db,
    init_db,
    RepairDocument,
    ChatSession,
    ChatMessage,
    FeedbackRecord,
)

__all__ = [
    "Base", "engine", "SessionLocal", "get_db", "init_db",
    "RepairDocument", "ChatSession", "ChatMessage", "FeedbackRecord",
]
