"""OrderViewSet: the orders of the user through the API.

    GET  /api/orders/              my orders (staff: all), 20 per page
    POST /api/orders/              a new order with its items
    GET  /api/orders/<pk>/         one order
    POST /api/orders/<pk>/cancel/  cancel my new unpaid order

No PUT / PATCH / DELETE: an order is a financial record. Its status is
changed by managers in the admin, the payment status by the payments.
No cart: the client sends the finished order (README: why).

Who sees what (get_queryset):
    customer  only own orders; someone else's -> 404, like a missing one
              (403 would tell that order #pk exists)
    staff     every order, for reading; "cancel" -> 403 (IsOwnerOrReadOnly)
"""

import logging

from django.db import IntegrityError
from django.db.models import Q, Sum
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from orders.models import Order
from orders.services import OrderError, cancel_order, create_order
from payments.models import Payment

from ..docs import (
    IDEMPOTENCY_KEY_PARAMETER,
    ORDER_CANCEL,
    ORDER_CANCEL_ERRORS,
    ORDER_CREATE,
    UNAUTHORIZED,
    order_list_schema,
)
from ..exceptions import Conflict, IdempotencyKeyReused
from ..permissions import IsOwnerOrReadOnly
from ..serializers.orders import OrderCreateSerializer, OrderSerializer

logger = logging.getLogger(__name__)  # "api.views.orders"

# The header of POST /api/orders/ (the name used by Stripe and the IETF
# draft "The Idempotency-Key HTTP Header Field")
IDEMPOTENCY_HEADER = "Idempotency-Key"
# Added to a repeated answer: "this is the order of your first request"
REPLAYED_HEADER = "Idempotent-Replayed"
IDEMPOTENCY_KEY_MAX_LENGTH = Order._meta.get_field("idempotency_key").max_length


@order_list_schema
class OrderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Only the actions an order allows: list, retrieve, create (+ cancel).

    A GenericViewSet with the mixins we need, instead of ModelViewSet
    without update / destroy: what is not in the class has no URL at all,
    PUT / PATCH / DELETE answer 405 Method Not Allowed.
    """

    serializer_class = OrderSerializer
    # Both: a login for everything, then the owner check for the changes
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    # ?status=new, ?payment_status=paid; ?ordering=total / -created_at
    filterset_fields = ["status", "payment_status"]
    ordering_fields = ["created_at", "total"]

    def get_queryset(self):
        # drf-spectacular calls this to build /api/docs/, without a real
        # request user (AnonymousUser): only the model is needed then
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        queryset = (
            Order.objects
            # The owner's name: a manager's list shows it for every order
            .select_related("user")
            # The lines and their books: 2 extra queries for the whole page
            .prefetch_related("items__book")
            # The paid sum in the same SQL query as the orders (LEFT JOIN
            # payments + GROUP BY + SUM ... FILTER), like the order_status
            # view of the site; not a SUM query per order
            .annotate(
                paid=Sum(
                    "payments__amount",
                    filter=Q(payments__status=Payment.Status.SUCCEEDED),
                )
            )
            # Explicit: Meta.ordering is dropped from GROUP BY queries;
            # "-pk" for equal dates (a stable order of the pages)
            .order_by("-created_at", "-pk")
        )
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    @extend_schema(
        request=OrderCreateSerializer,
        parameters=[IDEMPOTENCY_KEY_PARAMETER],
        responses={
            201: OrderSerializer,
            400: OpenApiResponse(description="Invalid fields or not enough copies."),
            401: UNAUTHORIZED,
            422: OpenApiResponse(description="The Idempotency-Key was used for another order."),
        },
        **ORDER_CREATE,
    )
    def create(self, request, *args, **kwargs):
        """POST /api/orders/: check the request, create the order, answer with it.

        Our own create() instead of CreateModelMixin's: the request and the
        answer have different serializers, and the order is made by
        orders.services.create_order(), not by serializer.save().

        Idempotency-Key (optional header, any unique text, e.g. a UUID):
            1st request with a key   -> 201, a new order, the key is saved with it
            the same key + same body -> 201 with the SAME order and the header
                                        "Idempotent-Replayed: true"; nothing new
                                        is created or reserved, no second email
            the same key + other body -> 422 (IdempotencyKeyReused)
        A request that failed (400, not enough copies) saves nothing, the key
        neither: it may be sent again with the same key.
        """
        key = self._idempotency_key(request)
        serializer = OrderCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)  # 400 with the errors of the fields

        # The usual repeat: the first request has finished long ago
        if key and (existing := self._order_by_key(key)) is not None:
            return self._replay(existing, serializer)

        data = serializer.validated_data
        try:
            order = create_order(
                request.user,
                serializer.quantities(),
                full_name=data["full_name"],
                phone=data["phone"],
                address=data["address"],
                idempotency_key=key,
            )
        except IntegrityError:
            # Two requests with the same key at the same moment: both found
            # no order above, the first one committed, the INSERT of this one
            # broke the unique constraint (its transaction is rolled back, the
            # stock is untouched). Answer with the order of the first one.
            existing = self._order_by_key(key) if key else None
            if existing is None:
                raise  # another constraint: a real error, 500
            return self._replay(existing, serializer)
        except OrderError as error:
            # Not enough copies (every book with a problem at once). 400 on
            # "items": the client changes the quantities and sends again.
            # Nothing is saved: create_order() rolled the transaction back.
            raise ValidationError({"items": error.messages})

        logger.info(
            "API order created: id=%s total=%s items=%s by user=%s",
            order.pk,
            order.total,
            len(serializer.quantities()),
            request.user.username,
        )
        if key:
            logger.info("API order id=%s idempotency key=%r", order.pk, key)
        # Read again through get_queryset(): the answer has the same
        # fields as GET /api/orders/<pk>/ (the paid sum, the lines with books)
        order = self.get_queryset().get(pk=order.pk)
        return Response(
            OrderSerializer(order, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    def _idempotency_key(self, request):
        """The Idempotency-Key header: "" without it; 400 if it is too long."""
        key = request.headers.get(IDEMPOTENCY_HEADER, "").strip()
        if len(key) > IDEMPOTENCY_KEY_MAX_LENGTH:
            raise ValidationError(
                {
                    IDEMPOTENCY_HEADER: [
                        _("At most %(max)s characters.") % {"max": IDEMPOTENCY_KEY_MAX_LENGTH}
                    ]
                }
            )
        return key

    def _order_by_key(self, key):
        """The order of THIS user with this key (with the lines), or None.

        Through get_queryset(), but filtered by the user also for staff:
        the keys are unique per user, a manager's key may be the same as
        a customer's one.
        """
        return self.get_queryset().filter(user=self.request.user, idempotency_key=key).first()

    def _replay(self, order, serializer):
        """The answer to a repeated request: the existing order, or 422.

        "The same request" = the same books and quantities and the same
        delivery data (after the cleaning of the serializer: "+380 67 ..."
        and "+38067..." are equal). The order is shown as it is NOW: a
        repeat after the payment shows "paid".
        """
        data = serializer.validated_data
        same = {item.book_id: item.quantity for item in order.items.all()} == (
            serializer.quantities()
        ) and (order.full_name, order.phone, order.address) == (
            data["full_name"],
            data["phone"],
            data["address"],
        )
        if not same:
            raise IdempotencyKeyReused()
        logger.info(
            "API order replayed: id=%s key=%r by user=%s",
            order.pk,
            order.idempotency_key,
            self.request.user.username,
        )
        return Response(
            OrderSerializer(order, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
            headers={REPLAYED_HEADER: "true"},
        )

    @extend_schema(
        request=None, responses={200: OrderSerializer, **ORDER_CANCEL_ERRORS}, **ORDER_CANCEL
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """POST /api/orders/<pk>/cancel/: the customer cancels a new unpaid order.

        The books go back to the stock, an open Stripe page is closed
        (orders.services.cancel_order, the same as the "Cancel" button).

        get_object(): the order from get_queryset() (someone else's -> 404)
        and check_object_permissions() -> IsOwnerOrReadOnly (staff -> 403).
        """
        order = self.get_object()
        try:
            cancel_order(order.pk, user=request.user)
        except OrderError as error:
            # Already cancelled / paid / being processed: the request is
            # right, the state of the order doesn't allow it -> 409
            raise Conflict(error.messages[0])

        logger.info("API order cancelled: id=%s by user=%s", order.pk, request.user.username)
        order = self.get_queryset().get(pk=order.pk)
        return Response(OrderSerializer(order, context=self.get_serializer_context()).data)
