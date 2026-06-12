"""
backend/routers/__init__.py
----------------------------
Makes `routers` a Python package and exports all routers.
FastAPI's main.py imports from here: `from backend.routers import chat, admin`
"""
from backend.routers import chat, admin

__all__ = ["chat", "admin"]
