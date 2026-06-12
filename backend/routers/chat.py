"""
backend/routers/chat.py
------------------------
FastAPI router for all chat-related HTTP endpoints.

WHAT IS A ROUTER?
In FastAPI, a "router" is a group of related endpoints.
We separate them into files to keep the code organized.
The main.py file then includes all routers.

ENDPOINTS:
- POST /api/chat        → Send a message, get a response (non-streaming)
- POST /api/chat/stream → Send a message, get streaming response
- GET  /api/history     → Get chat history for a session
- POST /api/feedback    → Submit feedback on a response
- GET  /api/stats       → Get session stats
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional
from loguru import logger

from backend.models.database import get_db, ChatMessage, FeedbackRecord
from backend.services.chat_service import chat_stream, chat_simple
from backend.utils.text_helpers import sanitize_input, extract_obd_codes, detect_vehicle_mention
from backend.utils.rate_limiter import rate_limit_check, chat_limiter

router = APIRouter(prefix="/api", tags=["chat"])


# ─────────────────────────────────────────────
# Request/Response Schemas
# ─────────────────────────────────────────────
# Pydantic models validate incoming request data automatically.
# If a required field is missing or wrong type, FastAPI returns 422.

class ChatRequest(BaseModel):
    message: str = Field(
        ...,  # ... means required
        min_length=1,
        max_length=2000,
        description="The user's message"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID. If not provided, a new session is created."
    )


class ChatResponse(BaseModel):
    response: str
    session_id: str


class FeedbackRequest(BaseModel):
    session_id: str
    message_id: str
    rating: int = Field(..., ge=-1, le=1, description="1=helpful, -1=not helpful")
    comment: Optional[str] = None


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    raw_request: Request,
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Standard (non-streaming) chat endpoint.
    Waits for the full response then returns it.

    Use this for: REST API clients, testing, simple integrations.
    """
    # Apply rate limiting — raises 429 if exceeded
    rate_limit_check(raw_request, chat_limiter)

    session_id = request.session_id or str(uuid.uuid4())

    # Sanitize and clean user input
    clean_message = sanitize_input(request.message)

    # Log any OBD codes or vehicle mentions for analytics
    obd_codes = extract_obd_codes(clean_message)
    vehicle = detect_vehicle_mention(clean_message)
    if obd_codes:
        logger.info(f"OBD codes detected: {obd_codes}")
    if vehicle:
        logger.info(f"Vehicle mention: {vehicle}")

    try:
        response = await chat_simple(db, clean_message, session_id)
        return ChatResponse(response=response, session_id=session_id)
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream_endpoint(
    raw_request: Request,
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Streaming chat endpoint.
    Returns response as Server-Sent Events (SSE) — chunks arrive as they're generated.

    Use this for: The Chainlit UI, any frontend that wants real-time streaming.
    """
    # Apply rate limiting
    rate_limit_check(raw_request, chat_limiter)

    session_id = request.session_id or str(uuid.uuid4())
    clean_message = sanitize_input(request.message)

    async def generate():
        yield f"data: [SESSION:{session_id}]\n\n"
        async for chunk in chat_stream(db, clean_message, session_id):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/history/{session_id}")
def get_history(
    session_id: str,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    Returns the conversation history for a session.
    Useful for displaying previous messages when a user returns.
    """
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    
    return {
        "session_id": session_id,
        "messages": [
            {
                "id": str(msg.id),
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat()
            }
            for msg in messages
        ]
    }


@router.post("/feedback")
def submit_feedback(
    request: FeedbackRequest,
    db: Session = Depends(get_db)
):
    """
    Stores user feedback for a specific response.
    This data is invaluable for improving the chatbot over time.
    """
    feedback = FeedbackRecord(
        session_id=request.session_id,
        message_id=request.message_id,
        rating=request.rating,
        comment=request.comment
    )
    db.add(feedback)
    db.commit()
    
    return {"status": "ok", "message": "Thank you for your feedback!"}


@router.get("/stats/{session_id}")
def get_session_stats(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Returns stats for a session."""
    count = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .count()
    )
    return {"session_id": session_id, "message_count": count}
