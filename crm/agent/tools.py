# crm/agent/tools.py
"""
LangChain tool definitions for the Xeno CRM agent.

Tools:
  1. segment_customers  — query DB and return audience size + preview
  2. draft_message      — call LLM to write marketing copy
  3. create_campaign    — create Segment + Campaign in DB
  4. get_stats          — fetch campaign delivery metrics
"""

import json
import logging

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


# ── 1. segment_customers ─────────────────────────────────────────────────────

@tool
def segment_customers(filters_json: str) -> str:
    """
    Find customers matching filter criteria and return a count + preview.

    Args:
        filters_json: JSON string with this structure:
            {
                "operator": "AND",
                "rules": [
                    {"field": "total_spent",   "operator": "gt",          "value": 5000},
                    {"field": "last_order_at", "operator": "lt_days_ago", "value": 90},
                    {"field": "city",          "operator": "eq",          "value": "Mumbai"}
                ]
            }

    Returns:
        JSON string with count and a preview of up to 5 customers.
    """
    from crm.services.segmentation import apply_filters

    try:
        filters = json.loads(filters_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    try:
        qs    = apply_filters(filters)
        count = qs.count()

        preview = list(
            qs.values("id", "name", "email", "city", "total_spent", "order_count")[:5]
        )

        # Convert Decimal to float for JSON serialisation
        for p in preview:
            p["total_spent"] = float(p["total_spent"])

        return json.dumps({
            "count":   count,
            "preview": preview,
            "filters": filters,
        })
    except Exception as exc:
        logger.error("segment_customers error: %s", exc)
        return json.dumps({"error": str(exc)})


# ── 2. draft_message ─────────────────────────────────────────────────────────

@tool
def draft_message(goal: str, segment_description: str, channel: str = "whatsapp") -> str:
    """
    Write a personalised marketing message for a customer segment.

    Args:
        goal                : What the campaign aims to achieve
                              (e.g. "win back dormant customers with a discount")
        segment_description : Description of the target audience
                              (e.g. "high-value customers who haven't ordered in 90 days")
        channel             : Delivery channel — "whatsapp", "sms", "email", or "rcs"

    Returns:
        A drafted marketing message with a {name} placeholder.
    """
    from django.conf import settings
    import os

    google_key = settings.GOOGLE_API_KEY or ""
    os.environ["GOOGLE_API_KEY"] = google_key

    llm    = ChatGoogleGenerativeAI(
        model          = "gemini-2.5-flash",
        temperature    = 0.7,
        google_api_key = google_key,
    )

    char_limits = {
        "sms":      160,
        "whatsapp": 1024,
        "email":    800,
        "rcs":      500,
    }
    max_chars = char_limits.get(channel, 300)

    prompt = f"""You are a world-class marketing copywriter for an Indian e-commerce brand.

Write a single marketing message for the following campaign:

Campaign Goal     : {goal}
Target Audience   : {segment_description}
Channel           : {channel.upper()} (max {max_chars} characters)

Rules:
- Start with "Hi {{name}}," or "Hey {{name}},"
- Use a friendly, conversational Indian English tone
- Include a clear call to action
- Add 1-2 relevant emojis
- Keep it under {max_chars} characters
- Use ₹ for rupee amounts
- Do NOT include URLs, only mention a discount code if relevant

Return ONLY the message text, nothing else."""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        message  = response.content.strip()
        return json.dumps({"message": message, "channel": channel})
    except Exception as exc:
        logger.error("draft_message error: %s", exc)
        return json.dumps({"error": str(exc)})


# ── 3. create_campaign ───────────────────────────────────────────────────────

@tool
def create_campaign(
    name: str,
    natural_query: str,
    filters_json: str,
    message_template: str,
    channel: str,
) -> str:
    """
    Create a new campaign in the CRM system.

    Args:
        name             : Campaign name (e.g. "Diwali Win-Back Mumbai VIPs")
        natural_query    : Human-readable description of the segment
                           (e.g. "High-value customers from Mumbai inactive for 90 days")
        filters_json     : JSON string of filter rules (same format as segment_customers)
        message_template : Message text with {name} placeholder
        channel          : "whatsapp" | "sms" | "email" | "rcs"

    Returns:
        JSON with the created campaign details including its ID.
    """
    from crm.services.campaign import create_campaign_from_agent

    try:
        filters = json.loads(filters_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid filters JSON: {exc}"})

    try:
        campaign = create_campaign_from_agent(
            name             = name,
            natural_query    = natural_query,
            filters          = filters,
            message_template = message_template,
            channel          = channel,
        )
        return json.dumps({
            "campaign_id":    campaign.id,
            "name":           campaign.name,
            "segment_id":     campaign.segment.id,
            "audience_size":  campaign.segment.customer_count,
            "channel":        campaign.channel,
            "status":         campaign.status,
            "message":        campaign.message_template,
        })
    except Exception as exc:
        logger.error("create_campaign error: %s", exc)
        return json.dumps({"error": str(exc)})


# ── 4. get_stats ─────────────────────────────────────────────────────────────

@tool
def get_stats(campaign_id: int) -> str:
    """
    Fetch live delivery and engagement statistics for a campaign.

    Args:
        campaign_id: The integer ID of the campaign

    Returns:
        JSON with sent, delivered, failed, read, clicked, ordered counts and rates.
    """
    from crm.services.campaign import get_campaign_stats

    try:
        stats = get_campaign_stats(campaign_id)
        return json.dumps(stats)
    except Exception as exc:
        logger.error("get_stats error: %s", exc)
        return json.dumps({"error": str(exc)})


# ── Tool registry ─────────────────────────────────────────────────────────────

ALL_TOOLS = [segment_customers, draft_message, create_campaign, get_stats]
