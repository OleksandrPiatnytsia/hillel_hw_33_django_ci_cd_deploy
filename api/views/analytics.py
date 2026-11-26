"""GET /api/analytics/orders/: every order for the backfill of Analytics.

Analytics gets new orders through the events (outbox -> RabbitMQ). The
orders made before the events existed it reads here, once, with its
command backfill_orders:

    POST /api/token/   {"username": "analytics-service", "password": ...}
    GET  /api/analytics/orders/?created_from=2026-01-01&page_size=500
         "Authorization: Bearer <access>"
    -> {"next": ".../?cursor=cD0xMjM%3D&page_size=500", "previous": null,
        "results": [{"order": {...}, "updated_at", "paid_at", "cancelled_at"}]}

Pages by a cursor, not by a page number: ?page=7 of a list that grows
while it is read would skip or repeat orders, the cursor "after id 123"
never does. The oldest orders first.

Who: the permission orders.export_orders_for_analytics (group Services,
the account of Analytics). No token -> 401, another account -> 403.
"""

import logging

from django.db.models import Exists, OuterRef, Subquery
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.pagination import CursorPagination

from orders.models import Order, OrderItem
from orders.reports import day_bounds
from outbox.models import OutboxEvent
from outbox.snapshot import items_prefetch

from ..docs import FORBIDDEN, UNAUTHORIZED
from ..permissions import CanExportOrdersForAnalytics
from ..serializers.analytics import AnalyticsOrderSerializer, AnalyticsOrdersQuerySerializer

logger = logging.getLogger(__name__)  # "api.views.analytics"


class AnalyticsOrdersPagination(CursorPagination):
    # By id: unique and never changes (created_at may repeat, the cursor
    # needs a column without ties)
    ordering = "id"
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


def event_moment(event_type):
    """The moment the first event of this type was recorded for the order, or NULL."""
    events = OutboxEvent.objects.filter(order_id=OuterRef("pk"), type=event_type)
    return Subquery(events.order_by("created_at").values("created_at")[:1])


@extend_schema(
    tags=["analytics"],
    summary="Orders for the backfill of Analytics",
    description=(
        "Every order with items, the oldest first, as the snapshot of the events "
        "(no personal data). For the service account of Analytics: permission "
        "orders.export_orders_for_analytics (group Services)."
    ),
    parameters=[AnalyticsOrdersQuerySerializer],
    responses={
        200: AnalyticsOrderSerializer(many=True),
        400: OpenApiResponse(description="A wrong date, or created_from > created_to."),
        401: UNAUTHORIZED,
        403: FORBIDDEN,
    },
)
class AnalyticsOrderListView(ListAPIView):
    serializer_class = AnalyticsOrderSerializer
    permission_classes = [CanExportOrdersForAnalytics]
    pagination_class = AnalyticsOrdersPagination
    # Not the filters / ?ordering of the default settings: the cursor
    # decides the order, the dates are checked by the serializer above
    filter_backends = []

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        query = AnalyticsOrdersQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)  # 400 with the reason

        queryset = (
            Order.objects
            # An order without items can't be a report line (an order whose
            # creation failed half way); Analytics would refuse it anyway
            .filter(Exists(OrderItem.objects.filter(order=OuterRef("pk")))).annotate(
                paid_at=event_moment(OutboxEvent.Type.ORDER_PAID),
                cancelled_at=event_moment(OutboxEvent.Type.ORDER_CANCELLED),
            )
            # The items with their books for the whole page: 3 queries, not
            # 4 per order (order_snapshot takes them from here)
            .prefetch_related(items_prefetch())
        )
        if first := query.validated_data.get("created_from"):
            queryset = queryset.filter(created_at__gte=day_bounds(first)[0])
        if last := query.validated_data.get("created_to"):
            # The half-open end: [.., the next midnight) catches 23:59:59.999
            queryset = queryset.filter(created_at__lt=day_bounds(last)[1])
        return queryset

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        logger.info(
            "Analytics backfill page: user=%s created_from=%s created_to=%s orders=%d",
            request.user.username,
            request.query_params.get("created_from", "-"),
            request.query_params.get("created_to", "-"),
            len(response.data["results"]),
        )
        return response
