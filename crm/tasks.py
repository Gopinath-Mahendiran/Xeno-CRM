# crm/tasks.py
"""
Celery tasks for Xeno CRM.

Tasks:
  fire_campaign_task(campaign_id) — fetch campaign audience → dispatch via channel service
"""

import logging
from celery import shared_task
from django.db import transaction

from crm.models import Campaign
from crm.services.segmentation import apply_filters_from_json
from crm.services.channel import dispatch_to_channel

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fire_campaign_task(self, campaign_id: int):
    """
    Background Celery task: fire a campaign to all customers in its segment.

    Flow:
      1. Load campaign + segment
      2. Apply segment filters → get customer QuerySet
      3. Update campaign status → 'running'
      4. Dispatch messages via channel service
      5. Update sent_count / failed_count on campaign
      6. Set campaign status → 'completed'
    """
    logger.info("🚀 Firing campaign %s", campaign_id)

    try:
        campaign = Campaign.objects.select_related("segment").get(pk=campaign_id)
    except Campaign.DoesNotExist:
        logger.error("Campaign %s not found — aborting task", campaign_id)
        return

    if campaign.status == "completed":
        logger.warning("Campaign %s already completed — skipping", campaign_id)
        return

    # Mark as running
    campaign.status = "running"
    campaign.save(update_fields=["status"])

    try:
        # Get audience from segment filter
        customers = apply_filters_from_json(campaign.segment.sql_filter)
        logger.info("  Audience size: %s customers", customers.count())

        # Dispatch
        result = dispatch_to_channel(campaign, customers)

        # Update campaign status atomically
        with transaction.atomic():
            campaign.refresh_from_db()
            campaign.status        = "completed"
            campaign.save(update_fields=["status"])

        logger.info(
            "✅ Campaign %s completed — sent=%s, failed=%s",
            campaign_id, result["sent"], result["failed"]
        )

    except Exception as exc:
        logger.error("Campaign %s failed: %s", campaign_id, exc)
        campaign.status = "draft"   # roll back to draft so it can be re-fired
        campaign.save(update_fields=["status"])
        raise self.retry(exc=exc)
