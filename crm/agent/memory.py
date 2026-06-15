# crm/agent/memory.py
"""
Redis-backed conversation history for the LangChain agent.

Uses Django's cache framework (already wired to Redis in settings.py).
Each session_id maps to a JSON list of {role, content} dicts.
"""

import json
from django.core.cache import cache
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage

HISTORY_TTL   = 60 * 60 * 2   # 2 hours
MAX_TURNS     = 10             # keep last 10 turns (20 messages)


def _cache_key(session_id: str) -> str:
    return f"xeno:chat:history:{session_id}"


def load_history(session_id: str) -> list[BaseMessage]:
    """Load conversation history from Redis for a given session.
    Falls back to DB if Redis cache is empty (cold-start recovery).
    """
    raw = cache.get(_cache_key(session_id))
    if raw:
        messages: list[BaseMessage] = []
        for item in raw:
            role    = item.get("role")
            content = item.get("content", "")
            if role == "human":
                messages.append(HumanMessage(content=content))
            elif role == "ai":
                messages.append(AIMessage(content=content))
            elif role == "system":
                messages.append(SystemMessage(content=content))
        return messages

    # Cold-start fallback: load from DB
    try:
        from crm.models import ChatSession
        session = ChatSession.objects.filter(session_id=session_id).first()
        if session:
            db_msgs = session.messages.all().order_by('created_at')
            messages = []
            for msg in db_msgs:
                if msg.role == 'human':
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == 'ai':
                    messages.append(AIMessage(content=msg.content))
            if messages:
                # Re-populate Redis cache
                save_history(session_id, messages)
            return messages
    except Exception:
        pass

    return []


def save_history(session_id: str, history: list[BaseMessage]) -> None:
    """Persist conversation history to Redis, trimmed to MAX_TURNS."""
    # Trim to keep only the last MAX_TURNS * 2 messages
    if len(history) > MAX_TURNS * 2:
        history = history[-(MAX_TURNS * 2):]

    serialisable = []
    for msg in history:
        if isinstance(msg, HumanMessage):
            serialisable.append({"role": "human", "content": msg.content})
        elif isinstance(msg, AIMessage):
            serialisable.append({"role": "ai",    "content": msg.content})
        elif isinstance(msg, SystemMessage):
            serialisable.append({"role": "system","content": msg.content})

    cache.set(_cache_key(session_id), serialisable, timeout=HISTORY_TTL)


def clear_history(session_id: str) -> None:
    """Clear conversation history for a session."""
    cache.delete(_cache_key(session_id))
