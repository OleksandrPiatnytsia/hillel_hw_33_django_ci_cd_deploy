"""Serializers of GET /api/analytics/orders/: the orders for the backfill of Analytics.

One item of the answer:

    {"order": {...the snapshot of the events: outbox/snapshot.py...},
     "updated_at": "2026-11-18T10:20:00Z",
     "paid_at": "2026-11-18T10:16:00Z",      or null
     "cancelled_at": null}

"order" is the same function the events use (order_snapshot), so Analytics
checks it with the same serializer and stores it with the same code. No
personal data: no name, phone, address, email or user id.
"""

from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from outbox.snapshot import order_snapshot


class AnalyticsOrdersQuerySerializer(serializers.Serializer):
    """?created_from=&created_to=: days of creation (UTC), both included, both optional."""

    created_from = serializers.DateField(
        required=False, help_text="First day of creation (YYYY-MM-DD, UTC), included."
    )
    created_to = serializers.DateField(
        required=False, help_text="Last day of creation (YYYY-MM-DD, UTC), included."
    )

    def validate(self, attrs):
        first, last = attrs.get("created_from"), attrs.get("created_to")
        if first and last and first > last:
            raise serializers.ValidationError(_("created_from is later than created_to."))
        return attrs


class AnalyticsOrderSerializer(serializers.Serializer):
    """An order of the queryset of AnalyticsOrderListView (with paid_at / cancelled_at)."""

    order = serializers.SerializerMethodField(
        help_text="The order snapshot of the events (contract version 1 of Analytics)."
    )
    updated_at = serializers.DateTimeField(help_text="The last change of the order.")
    # From the outbox: when the event "paid" / "cancelled" was recorded. Null
    # for the orders older than the outbox (version 1.5.0) or whose events
    # were already cleaned up; Analytics takes updated_at then
    paid_at = serializers.DateTimeField(allow_null=True)
    cancelled_at = serializers.DateTimeField(allow_null=True)

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_order(self, order):
        return order_snapshot(order)
