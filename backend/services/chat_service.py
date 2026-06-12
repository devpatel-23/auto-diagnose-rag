"""
backend/services/chat_service.py
----------------------------------
The core brain of the chatbot — the RAG (Retrieval Augmented Generation) pipeline.

THE FLOW:
  User message
      ↓
  1. Retrieve relevant repair knowledge from pgvector
      ↓
  2. Load recent conversation history from PostgreSQL
      ↓
  3. Build a prompt: system instructions + knowledge + history + user message
      ↓
  4. Send to OpenAI GPT-4o
      ↓
  5. Stream the response back to the user
      ↓
  6. Save user message + assistant response to database

WHY RAG?
Without RAG, the bot can only use what GPT was trained on — which may be outdated,
generic, or missing model-specific info. RAG lets the bot reference YOUR knowledge
base (repair manuals, OBD codes, etc.) for accurate, specific answers.
"""

import uuid
from typing import AsyncGenerator, List, Dict
from loguru import logger
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.database import ChatMessage, ChatSession
from backend.services.vector_store import search_similar_chunks, format_context_for_prompt

# Initialize fast Groq model for chat
# (Make sure GROQ_API_KEY is in your .env file)
chat_model = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.3,
    max_tokens=1500,
    api_key=settings.groq_api_key
)

# System Prompt

SYSTEM_PROMPT = """You are AutoMechAI, an expert vehicle repair and restoration assistant with 30+ years of combined knowledge.

Your expertise covers:
- Engine diagnostics and repair (gasoline and diesel)
- Transmission and drivetrain systems
- Brakes, suspension, and steering
- Electrical systems and OBD-II fault codes
- Classic vehicle restoration and restomod builds
- Preventive maintenance and service schedules

RESPONSE GUIDELINES:
1. Be specific and practical — give real repair procedures, not vague advice.
2. Always mention safety warnings for dangerous procedures (high voltage, exhaust gases, spring compression, etc.).
3. When diagnosing, work from most likely/cheapest fix to most complex/expensive.
4. Mention if a repair requires professional tools or skills.
5. Use the provided repair knowledge context to give accurate, specific answers.
6. If the context doesn't cover the question, say so clearly — never fabricate repair specs or torque values.
7. For safety-critical systems (brakes, steering, suspension), always recommend professional inspection if uncertain.
8. Format responses clearly with numbered steps for procedures.
9. Include approximate costs when helpful (parts + labor ranges).

TONE: Professional but approachable. Like talking to a trusted master mechanic, not reading a manual.

IMPORTANT: If asked about a specific vehicle (make/model/year), factor that into your answer — repair procedures often differ significantly between vehicles."""


# Conversation History

def get_conversation_history(db: Session, session_id: str, limit: int = 10) -> List[Dict]:
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    
    return [{"role": msg.role, "content": msg.content} for msg in messages]


def save_messages(
    db: Session,
    session_id: str,
    user_message: str,
    assistant_message: str
) -> None:
    """
    Saves both the user's message and the bot's response to the database.
    Also updates the session's last_active timestamp and message count.
    """
    # Save user message
    db.add(ChatMessage(
        session_id=session_id,
        role="user",
        content=user_message
    ))
    
    # Save assistant response
    db.add(ChatMessage(
        session_id=session_id,
        role="assistant",
        content=assistant_message
    ))
    
    # Update session stats
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id
    ).first()
    
    if session:
        session.message_count += 2
    
    db.commit()


def ensure_session_exists(db: Session, session_id: str) -> None:
    """Creates a session record if it doesn't already exist."""
    import uuid as uuid_lib
    # Generate a proper UUID from the session string if needed
    try:
        valid_id = str(uuid_lib.UUID(session_id))
    except ValueError:
        valid_id = str(uuid_lib.uuid5(uuid_lib.NAMESPACE_DNS, session_id))
    
    existing = db.query(ChatSession).filter(
        ChatSession.id == valid_id
    ).first()
    
    if not existing:
        db.add(ChatSession(id=valid_id))
        db.commit()


# The RAG Pipeline (Streaming)

async def chat_stream(
        db: Session,
        user_message: str,
        session_id: str
) -> AsyncGenerator[str, None]:
    """
    Main chat function that returns a streaming response using Groq.
    """

    # ── Step 1: Ensure session exists
    ensure_session_exists(db, session_id)

    # ── Step 2: Vector search
    logger.info(f"Searching for context: '{user_message[:60]}...'")

    try:
        relevant_chunks = search_similar_chunks(db, user_message, top_k=5)
        context = format_context_for_prompt(relevant_chunks)
        logger.info(f"Found {len(relevant_chunks)} relevant chunks")
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        context = ""

        # ── Step 3: Build message history
    history_dicts = get_conversation_history(db, session_id, limit=10)

    # ── Step 4: Construct the LangChain Prompt
    messages = [
        SystemMessage(content=SYSTEM_PROMPT)
    ]

    # Add repair knowledge as additional context (if found)
    if context:
        messages.append(
            SystemMessage(
                content=f"RELEVANT REPAIR KNOWLEDGE FROM DATABASE:\n{context}\n\nUse this knowledge to inform your response. If it directly answers the question, reference it.")
        )

    # Translate historical DB dictionaries into LangChain Message objects
    for msg in history_dicts:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    # Add the current user message
    messages.append(HumanMessage(content=user_message))

    # ── Step 5: Stream from Groq ─────────────────
    full_response = ""

    try:
        # astream() is LangChain's method for async streaming
        async for chunk in chat_model.astream(messages):
            if chunk.content:
                full_response += chunk.content
                yield chunk.content  # Send to frontend immediately

    except Exception as e:
        error_msg = f"I'm having trouble connecting right now. Please try again. (Error: {str(e)[:100]})"
        logger.error(f"Groq API error: {e}")
        yield error_msg
        full_response = error_msg

    # ── Step 6: Save to database ──────────────────
    if full_response and full_response != "":
        try:
            save_messages(db, session_id, user_message, full_response)
        except Exception as e:
            logger.error(f"Failed to save messages: {e}")


async def chat_simple(
    db: Session,
    user_message: str,
    session_id: str
) -> str:
    """
    Non-streaming version — returns the full response at once.
    Used by the REST API endpoint (for integrations, testing, etc.)
    """
    full_response = ""
    async for chunk in chat_stream(db, user_message, session_id):
        full_response += chunk
    return full_response
