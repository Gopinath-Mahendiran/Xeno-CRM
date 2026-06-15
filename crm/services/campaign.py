# crm/services/campaign.py
"""
Campaign service — creates Segment + Campaign atomically.
Called by the agent's create_campaign tool.
"""

import json
from django.db import transaction
from crm.models import Segment, Campaign
from crm.services.segmentation import apply_filters


def create_campaign_from_agent(
    name: str,
    natural_query: str,
    filters: dict,
    message_template: str,
    channel: str,
) -> Campaign:
    """
    Atomically:
      1. Create (or update) a Segment from the filter dict
      2. Count matching customers
      3. Create a Campaign in 'draft' status

    Args:
        name             : Campaign name (e.g. "Win-back Mumbai VIPs")
        natural_query    : Human-readable segment description
        filters          : Filter dict  {"operator": "AND", "rules": [...]}
        message_template : Message body with {name} placeholder
        channel          : "whatsapp" | "sms" | "email" | "rcs"

    Returns:
        Campaign instance
    """
    with transaction.atomic():
        # Count matching customers
        qs             = apply_filters(filters)
        customer_count = qs.count()

        # Create segment
        segment = Segment.objects.create(
            name           = f"[Agent] {name}",
            natural_query  = natural_query,
            sql_filter     = json.dumps(filters),
            customer_count = customer_count,
        )

        # Create campaign in draft
        campaign = Campaign.objects.create(
            name             = name,
            segment          = segment,
            message_template = message_template,
            channel          = channel,
            status           = "draft",
        )

    return campaign


def get_campaign_stats(campaign_id: int) -> dict:
    """Return a stats dict for a given campaign ID."""
    try:
        c = Campaign.objects.get(pk=campaign_id)
    except Campaign.DoesNotExist:
        return {"error": f"Campaign {campaign_id} not found"}

    return {
        "id":             c.id,
        "name":           c.name,
        "status":         c.status,
        "channel":        c.channel,
        "sent":           c.sent_count,
        "delivered":      c.delivered_count,
        "failed":         c.failed_count,
        "read":           c.read_count,
        "clicked":        c.clicked_count,
        "ordered":        c.order_count,
        "delivery_rate":  c.delivery_rate,
        "read_rate":      c.read_rate,
        "click_rate":     c.click_rate,
        "segment":        c.segment.name,
        "audience_size":  c.segment.customer_count,
    }


def _update_campaign_counter(campaign: Campaign, old_status: str, new_status: str):
    """Atomically update campaign aggregate counters based on status transition."""
    COUNTER_MAP = {
        "sent":      "sent_count",
        "failed":    "failed_count",
        "delivered": "delivered_count",
        "read":      "read_count",
        "clicked":   "clicked_count",
        "ordered":   "order_count",
    }

    field = COUNTER_MAP.get(new_status)
    if not field:
        return

    from django.db.models import F
    with transaction.atomic():
        Campaign.objects.filter(pk=campaign.pk).update(
            **{field: F(field) + 1}
        )

