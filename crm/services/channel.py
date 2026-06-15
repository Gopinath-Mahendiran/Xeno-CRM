# crm/services/channel.py
"""
Channel dispatch service.

For each customer in a campaign's segment:
  1. Render the personalised message
  2. Create a CommunicationLog entry (status=pending)
  3. POST to the channel_service microservice

The channel_service simulates async delivery and POSTs back to
/api/receipts/ with status updates.
"""

import logging
import requests
from django.conf import settings

from crm.models import Campaign, CommunicationLog, Customer

logger = logging.getLogger(__name__)


def render_message(template: str, customer: Customer) -> str:
    """Render a personalised message for a specific customer."""
    first_name = customer.name.split()[0]
    return (
        template
        .replace("{name}",      first_name)
        .replace("{name_slug}", first_name.lower())
        .replace("{city}",      customer.city or "your city")
    )


def dispatch_to_channel(campaign: Campaign, customers) -> dict:
    """
    Dispatch messages to all customers via the channel service.

    Args:
        campaign  : Campaign instance
        customers : QuerySet or list of Customer objects

    Returns:
        dict with sent_count and failed_count
    """
    channel_url = f"{settings.CHANNEL_SERVICE_URL}/send"
    receipt_url = f"{settings.CRM_BASE_URL}/api/receipts/"

    logs        = []
    payloads    = []

    for customer in customers:
        body = render_message(campaign.message_template, customer)
        log  = CommunicationLog(
            campaign     = campaign,
            customer     = customer,
            channel      = campaign.channel,
            message_body = body,
            status       = "pending",
        )
        logs.append(log)
        payloads.append({
            "message_id":  str(log.message_id),
            "to":          customer.phone if campaign.channel in ("sms", "whatsapp", "rcs") else customer.email,
            "channel":     campaign.channel,
            "body":        body,
            "receipt_url": receipt_url,
        })

    # Bulk create all logs
    CommunicationLog.objects.bulk_create(logs)

    from django.db import transaction
    from crm.services.campaign import _update_campaign_counter

    sent   = 0
    failed = 0

    for payload in payloads:
        try:
            resp = requests.post(
                channel_url,
                json    = payload,
                timeout = 5,
            )
            if resp.status_code == 200:
                sent += 1
            else:
                failed += 1
                logger.warning(
                    "Channel service returned %s for message %s",
                    resp.status_code, payload["message_id"]
                )
                with transaction.atomic():
                    CommunicationLog.objects.filter(message_id=payload["message_id"]).update(status="failed")
                    _update_campaign_counter(campaign, "pending", "failed")
        except requests.RequestException as exc:
            failed += 1
            logger.error("Channel service error for %s: %s", payload["message_id"], exc)
            with transaction.atomic():
                CommunicationLog.objects.filter(message_id=payload["message_id"]).update(status="failed")
                _update_campaign_counter(campaign, "pending", "failed")

    return {"sent": sent, "failed": failed}
