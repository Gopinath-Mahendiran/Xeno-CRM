# crm/agent/agent.py
"""
Xeno CRM LangChain Agent.

Uses Google Gemini (gemini-2.0-flash) with tool-calling via langchain-google-genai.
Conversation history is stored in Redis per session.

Public API:
    run_agent(message, session_id) -> dict
"""

import logging
from typing import Any

from django.conf import settings

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.messages import HumanMessage, AIMessage

from crm.agent.prompts import SYSTEM_PROMPT
from crm.agent.memory import load_history, save_history
from crm.agent.tools import ALL_TOOLS

logger = logging.getLogger(__name__)


def _build_agent_executor() -> AgentExecutor:
    """Build and return a fresh AgentExecutor instance."""
    import os
    if settings.USE_LOCAL_LLM:
        logger.info("Using local LLM (%s: %s)", settings.LOCAL_LLM_PROVIDER, settings.LOCAL_LLM_MODEL)
        if settings.LOCAL_LLM_PROVIDER == 'ollama':
            from langchain_openai import ChatOpenAI
            base_url = settings.LOCAL_LLM_API_BASE
            if not base_url.endswith('/v1') and not base_url.endswith('/v1/'):
                base_url = base_url.rstrip('/') + '/v1'
            llm = ChatOpenAI(
                model       = settings.LOCAL_LLM_MODEL,
                base_url    = base_url,
                api_key     = settings.LOCAL_LLM_API_KEY or "ollama",
                temperature = 0,
            )
        elif settings.LOCAL_LLM_PROVIDER == 'openai':
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model       = settings.LOCAL_LLM_MODEL,
                base_url    = settings.LOCAL_LLM_API_BASE,
                api_key     = settings.LOCAL_LLM_API_KEY,
                temperature = 0,
            )
        else:
            raise ValueError(f"Unsupported local LLM provider: {settings.LOCAL_LLM_PROVIDER}")
    else:
        logger.info("Using production Google Gemini LLM")
        google_key = settings.GOOGLE_API_KEY or ""
        if not google_key:
            raise ValueError("GOOGLE_API_KEY is not set in .env")

        # Explicitly set env var so langchain-google-genai always finds it
        os.environ["GOOGLE_API_KEY"] = google_key

        llm = ChatGoogleGenerativeAI(
            model          = "gemini-2.5-flash",
            temperature    = 0,
            google_api_key = google_key,
            max_retries    = 1,   # fail fast — don't wait 32s × 5 retries on quota errors
        )


    prompt = ChatPromptTemplate.from_messages([
        ("system",   SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human",    "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(
        llm     = llm,
        tools   = ALL_TOOLS,
        prompt  = prompt,
    )

    return AgentExecutor(
        agent              = agent,
        tools              = ALL_TOOLS,
        verbose            = True,
        handle_parsing_errors = True,
        max_iterations     = 5,
        return_intermediate_steps = True,
    )


def run_agent(message: str, session_id: str = "default") -> dict[str, Any]:
    """
    Run the Xeno CRM agent for a given user message.

    Args:
        message    : The marketer's input message
        session_id : Session ID used to load/save conversation history

    Returns:
        {
            "reply":       str,   # agent's text response
            "tool_used":   str | None,
            "tool_result": Any | None,
            "session_id":  str,
        }
    """
    # 1. Load history from Redis
    history = load_history(session_id)

    # 2. Build executor
    executor = _build_agent_executor()

    # 3. Run
    try:
        result = executor.invoke({
            "input":        message,
            "chat_history": history,
        })
    except Exception as exc:
        logger.error("Agent execution error: %s", exc)
        return {
            "reply":       "I encountered an error processing your request. Please try again.",
            "tool_used":   None,
            "tool_result": None,
            "session_id":  session_id,
        }

    # 4. Extract reply and tool information
    reply       = result.get("output", "")
    tool_used   = None
    tool_result = None

    intermediate = result.get("intermediate_steps", [])
    if intermediate:
        last_step   = intermediate[-1]
        tool_used   = last_step[0].tool if hasattr(last_step[0], "tool") else None
        tool_result = last_step[1]

    # 5. Update history
    history.append(HumanMessage(content=message))
    history.append(AIMessage(content=reply))
    save_history(session_id, history)

    return {
        "reply":       reply,
        "tool_used":   tool_used,
        "tool_result": tool_result,
        "session_id":  session_id,
    }
