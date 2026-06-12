"""
backend/services/__init__.py
------------------------------
Makes `services` a Python package.
Services are the business logic layer — they sit between routers and the DB/APIs.
"""
from backend.services import vector_store, chat_service

__all__ = ["vector_store", "chat_service"]
