"""Serializers of orders: reading an order and creating one with its items.

Reading (GET /api/orders/, /api/orders/<pk>/):

    {"id": 12, "status": "new", "status_display": "Нове",
     "payment_status": "unpaid", ..., "total": "501.00",
     "paid_amount": "0.00", "amount_due": "501.00",
     "items": [{"book": {"id": 7, "title": "Kobzar"}, "title": "Kobzar",
                "price": "250.50", "quantity": 2, "cost": "501.00"}],
     "can_be_cancelled": true,
     "site_url": "http://localhost:8000/orders/12/"}

Creating (POST /api/orders/): the delivery data and the items at once,
there is no cart in the API (README: why):

    {"full_name": "Ann Shevchenko", "phone": "+380 67 123 45 67",
     "address": "Kyiv, Khreshchatyk 1",
     "items": [{"book_id": 7, "quantity": 2}, {"book_id": 9, "quantity": 1}]}

The prices, the total and the statuses are never taken from the request:
orders.services.create_order() sets them, the same function as the
checkout of the site (locks, stock reservation, the email after COMMIT).
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from books.models import Book
from orders.models import Order, OrderItem
from users.phone import normalize_phone


class OrderedBookSerializer(serializers.ModelSerializer):
    """The book of an order line: a link to the catalog (/api/books/<id>/)."""

    class Meta:
        model = Book
        fields = ["id", "title"]


class OrderItemSerializer(serializers.ModelSerializer):
    """One line of an order, as it was at the moment of ordering.

    title and price are the copies saved in OrderItem (the book may be
    renamed or cost more today); "book" is the current book.
    """

    book = OrderedBookSerializer(read_only=True)
    cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["book", "title", "price", "quantity", "cost"]


class OrderSerializer(serializers.ModelSerializer):
    """An order for reading: statuses, delivery data, money and the items."""

    items = OrderItemSerializer(many=True, read_only=True)
    # The owner: a manager sees the orders of everybody
    user = serializers.CharField(source="user.username", read_only=True)
    # The labels in the language of the request (Accept-Language):
    # "Нове" / "New". The codes ("new") are for the logic of a client
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_status_display = serializers.CharField(
        source="get_payment_status_display", read_only=True
    )
    paid_amount = serializers.SerializerMethodField()
    amount_due = serializers.SerializerMethodField()
    can_be_cancelled = serializers.BooleanField(
        source="can_be_cancelled_by_customer", read_only=True
    )
    site_url = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "status",
            "status_display",
            "payment_status",
            "payment_status_display",
            "full_name",
            "phone",
            "address",
            "total",
            "paid_amount",
            "amount_due",
            "items",
            "can_be_cancelled",
            "site_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _paid(self, order):
        # "paid" comes from the queryset of OrderViewSet (SUM of the
        # succeeded payments, in the same SQL query as the orders); a just
        # created order has no payments yet
        paid = getattr(order, "paid", None)
        return paid if paid is not None else Decimal("0.00")

    # The return type: drf-spectacular shows them as strings with a
    # decimal, like the other money fields
    def get_paid_amount(self, order) -> Decimal:
        return self._paid(order)

    def get_amount_due(self, order) -> Decimal:
        return max(order.total - self._paid(order), Decimal("0.00"))

    def get_site_url(self, order) -> str:
        """The order page on the site, with the "Pay" button.

        Payment is not in the API: Stripe Checkout is a page for a person,
        the customer opens this link and pays there.
        """
        return settings.SITE_URL + order.get_absolute_url()

    def to_representation(self, order):
        data = super().to_representation(order)
        # The same format as total ("501.00"), not a number
        for field in ("paid_amount", "amount_due"):
            data[field] = f"{data[field]:.2f}"
        return data


class OrderItemCreateSerializer(serializers.Serializer):
    """One line of a new order: which book and how many."""

    # An unknown id -> 400 for this line: "Invalid pk "999" - object does not exist."
    book_id = serializers.PrimaryKeyRelatedField(queryset=Book.objects.all())
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    """POST /api/orders/: the delivery data + the items.

    Only checks the request; the order itself is made by the view with
    orders.services.create_order() (the stock check is there, under the
    lock of the books: it can't be done here, before the lock).
    """

    full_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=30)
    address = serializers.CharField()
    # A nested serializer with many=True: a list of objects, each one
    # checked by OrderItemCreateSerializer
    items = OrderItemCreateSerializer(many=True, allow_empty=False)

    def validate_full_name(self, value):
        return " ".join(value.split())  # extra spaces out, like CheckoutForm

    def validate_phone(self, value):
        # The same check and format as the checkout form and the profile:
        # "+380 (67) 123-45-67" -> "+380671234567"
        # An empty value never comes here: CharField (allow_blank=False)
        # answers "This field may not be blank." itself
        try:
            return normalize_phone(value)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages)

    def validate_items(self, items):
        # One line per book (OrderItem has a unique constraint on it):
        # 3 copies = quantity 3, not the same book three times
        book_ids = [item["book_id"].pk for item in items]
        if len(book_ids) != len(set(book_ids)):
            raise serializers.ValidationError(
                _("Every book may be in the list only once; use quantity.")
            )
        return items

    def quantities(self):
        """{book_id: quantity}: the format of create_order() (and of the cart)."""
        return {item["book_id"].pk: item["quantity"] for item in self.validated_data["items"]}
