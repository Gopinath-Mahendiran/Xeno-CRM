# crm/services/segmentation.py
"""
Segmentation engine — converts JSON filter rules into Django ORM queries.

Filter format (same as Segment.sql_filter):
{
    "operator": "AND" | "OR",
    "rules": [
        {"field": "total_spent",   "operator": "gt",          "value": 5000},
        {"field": "last_order_at", "operator": "lt_days_ago", "value": 90},
        {"field": "city",          "operator": "eq",          "value": "Mumbai"},
        ...
    ]
}

Supported fields   : total_spent, order_count, last_order_at, created_at, city
Supported operators: gt, lt, gte, lte, eq, ne, lt_days_ago, gt_days_ago
"""

import json
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from crm.models import Customer


# ── Field → ORM lookup map ────────────────────────────────────────────────────
_FIELD_MAP = {
    "total_spent":   "total_spent",
    "order_count":   "order_count",
    "last_order_at": "last_order_at",
    "created_at":    "created_at",
    "city":          "city",
}

_OP_MAP = {
    "gt":  "__gt",
    "lt":  "__lt",
    "gte": "__gte",
    "lte": "__lte",
    "eq":  "",          # exact match — no suffix
    "ne":  "",          # handled separately
}


def _rule_to_q(rule: dict) -> Q:
    """Convert a single rule dict to a Django Q object."""
    field    = rule.get("field")
    operator = rule.get("operator")
    value    = rule.get("value")

    if field not in _FIELD_MAP:
        raise ValueError(f"Unknown filter field: '{field}'")

    orm_field = _FIELD_MAP[field]
    now       = timezone.now()

    if operator == "lt_days_ago":
        # field < (now - N days) — i.e., more than N days ago
        cutoff = now - timedelta(days=int(value))
        return Q(**{f"{orm_field}__lt": cutoff})

    if operator == "gt_days_ago":
        # field > (now - N days) — i.e., within the last N days
        cutoff = now - timedelta(days=int(value))
        return Q(**{f"{orm_field}__gt": cutoff})

    if operator == "ne":
        return ~Q(**{orm_field: value})

    if operator not in _OP_MAP:
        raise ValueError(f"Unknown filter operator: '{operator}'")

    suffix    = _OP_MAP[operator]
    lookup    = f"{orm_field}{suffix}"
    return Q(**{lookup: value})


def apply_filters(filters: dict) -> "QuerySet[Customer]":
    """
    Apply a filter dict to return a Customer QuerySet.

    Args:
        filters: dict with keys 'operator' and 'rules'

    Returns:
        Django QuerySet of matching Customer objects
    """
    rules    = filters.get("rules", [])
    operator = filters.get("operator", "AND").upper()

    if not rules:
        return Customer.objects.all()

    combined = None
    for rule in rules:
        q = _rule_to_q(rule)
        if combined is None:
            combined = q
        elif operator == "OR":
            combined = combined | q
        else:
            combined = combined & q

    if combined is None:
        return Customer.objects.all()

    return Customer.objects.filter(combined)


def apply_filters_from_json(sql_filter_json: str) -> "QuerySet[Customer]":
    """Convenience wrapper: accepts a JSON string (as stored in Segment.sql_filter)."""
    filters = json.loads(sql_filter_json)
    return apply_filters(filters)
