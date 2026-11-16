"""Serializers of orders: reading an order and creating one with its items.

Reading (GET /api/orders/, /api/orders/<pk>/):

    {"id": 12, "status": "new", "status_display": "Нове",
     "payment_status": "unpaid", ..., "currency": "USD",
     "exchange_rate": "45.427400", "total": "11.04",
     "paid_amount": "0.00", "amount_due": "11.04",
     "items": [{"book": {"id": 7, "title": "Kobzar"},
                "format": {"id": 12, "format_type": "ebook",
                           "format_type_display": "Електронна"},
                "title": "Kobzar", "price": "5.52", "original_price": "250.50",
                "original_currency": "UAH", "quantity": 2, "cost": "11.04"}],
     "can_be_cancelled": true,
     "site_url": "http://localhost:8000/orders/12/"}

Creating (POST /api/orders/): the delivery data and the items at once,
there is no cart in the API (README: why):

    {"full_name": "Ann Shevchenko", "phone": "+380 67 123 45 67",
     "address": "Kyiv, Khreshchatyk 1", "currency": "USD",
     "items": [{"format_id": 12, "quantity": 2}, {"book_id": 9, "quantity": 1}]}

A line names a format (paper, e-book, audiobook of a book: "formats" of
/api/books/). "book_id" is a short form for a book with ONE format on
sale; a book sold in several formats needs "format_id" (400 otherwise:
the API doesn't choose the format for the client).

All the money of an order (prices, total, paid, due) is in its currency,
chosen once at creation ("UAH" without "currency"); the formats are
converted at the NBU rate of that day and the order keeps the rates.
The prices, the total and the statuses are never taken from the request:
orders.services.create_order() sets them, the same function as the
checkout of the site (locks, stock reservation, the email after COMMIT).
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from books.models import Book, BookFormat
from currencies.models import BASE_CURRENCY
from currencies.services import available_currencies
from orders.models import Order, OrderItem
from users.phone import normalize_phone


class OrderedBookSerializer(serializers.ModelSerializer):
    """The book of an order line: a link to the catalog (/api/books/<id>/)."""

    class Meta:
        model = Book
        fields = ["id", "title"]


class OrderedFormatSerializer(serializers.Serializer):
    """The format of an order line: its id and the type bought."""

    id = serializers.IntegerField(source="format_id")
    format_type = serializers.CharField()
    format_type_display = serializers.CharField(source="get_format_type_display")


class OrderItemSerializer(serializers.ModelSerializer):
    """One line of an order, as it was at the moment of ordering.

    title and price are the copies saved in OrderItem (the book may be
    renamed or cost more today); "book" is the current book. price and cost
    are in the order currency; original_price + original_currency: the
    price of the book in its own currency then (the same when nothing was
    converted).
    """

    book = OrderedBookSerializer(read_only=True)
    # source="*": built from the line itself, from its copy of the type
    # (what was bought, even if the format is changed later), no query
    format = OrderedFormatSerializer(source="*", read_only=True)
    cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    original_currency = serializers.CharField(source="original_currency_id", read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "book",
            "format",
            "title",
            "price",
            "original_price",
            "original_currency",
            "quantity",
            "cost",
        ]


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
    # The code, not an object: the symbol and the rate are in /api/currencies/
    currency = serializers.CharField(source="currency_id", read_only=True)

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
            "currency",
            "exchange_rate",
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
    """One line of a new order: which format and how many.

        {"format_id": 12, "quantity": 2}   the format (from "formats" of a book)
        {"book_id": 7, "quantity": 2}      a book with one format on sale

    validate() puts the chosen BookFormat into attrs["format"].
    """

    # An unknown id -> 400 for this line: "Invalid pk "999" - object does not exist."
    format_id = serializers.PrimaryKeyRelatedField(
        queryset=BookFormat.objects.select_related("book"), required=False
    )
    book_id = serializers.PrimaryKeyRelatedField(queryset=Book.objects.all(), required=False)
    quantity = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        book_format, book = attrs.get("format_id"), attrs.get("book_id")
        if book_format is None and book is None:
            raise serializers.ValidationError(_("Send “format_id” (or “book_id”)."))
        if book_format is not None and book is not None:
            raise serializers.ValidationError(_("Send either “format_id” or “book_id”, not both."))

        if book_format is not None:
            if not book_format.is_active:
                raise serializers.ValidationError(
                    {"format_id": [_("“%(title)s” is not on sale.") % {"title": book_format}]}
                )
        else:
            # The formats on sale (one query per line): with one of them the
            # choice is clear; with several the client must choose, a
            # silent "paper" could sell the wrong thing
            formats = book.active_formats
            if not formats:
                raise serializers.ValidationError(
                    {"book_id": [_("“%(title)s” is not on sale.") % {"title": book.title}]}
                )
            if len(formats) > 1:
                raise serializers.ValidationError(
                    {
                        "book_id": [
                            _(
                                "“%(title)s” is sold in several formats (%(formats)s): "
                                "send “format_id”."
                            )
                            % {
                                "title": book.title,
                                "formats": ", ".join(
                                    f"{f.pk} — {f.get_format_type_display()}" for f in formats
                                ),
                            }
                        ]
                    }
                )
            book_format = formats[0]
        attrs["format"] = book_format
        return attrs


class OrderCreateSerializer(serializers.Serializer):
    """POST /api/orders/: the delivery data + the items.

    Only checks the request; the order itself is made by the view with
    orders.services.create_order() (the stock check is there, under the
    lock of the books: it can't be done here, before the lock).
    """

    full_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=30)
    address = serializers.CharField()
    # The currency of the order: a code from /api/currencies/. A CharField
    # checked in validate_currency(), not a ChoiceField with the choices
    # read in __init__: the serializer is also created to build the API
    # schema (/api/docs/, check --deploy), where the rates (cache, Redis)
    # must not be needed.
    currency = serializers.CharField(required=False, default=BASE_CURRENCY, max_length=3)
    # A nested serializer with many=True: a list of objects, each one
    # checked by OrderItemCreateSerializer
    items = OrderItemCreateSerializer(many=True, allow_empty=False)

    def validate_currency(self, value):
        """Only the currencies offered today: the switcher of the site, /api/currencies/."""
        code = value.strip().upper()
        offered = [currency.code for currency in available_currencies()]
        if code not in offered:
            raise serializers.ValidationError(
                _("“%(code)s” is not offered. Choose one of: %(offered)s.")
                % {"code": code, "offered": ", ".join(offered)}
            )
        return code

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
        # One line per format: 3 copies = quantity 3, not the same format three
        # times (also when one line names it by book_id, the other by format_id)
        format_ids = [item["format"].pk for item in items]
        if len(format_ids) != len(set(format_ids)):
            raise serializers.ValidationError(
                _("Every format may be in the list only once; use quantity.")
            )
        return items

    def quantities(self):
        """{format_id: quantity}: the format of create_order() (and of the cart)."""
        return {item["format"].pk: item["quantity"] for item in self.validated_data["items"]}

    def same_items(self, order_items):
        """Are these lines of an order the lines of this request? (the idempotency check)

        Compared as the request names them: a "format_id" line with the
        format of the order line, a "book_id" line with its book. The format
        of a book_id line is chosen now and may be another one than at the
        first request (a format turned off, a new one added), the book is
        the same. Two order lines of one book can't match one book_id line.
        """
        requested = {}
        for item in self.validated_data["items"]:
            if "format_id" in item:
                requested["format", item["format"].pk] = item["quantity"]
            else:
                requested["book", item["book_id"].pk] = item["quantity"]
        ordered = {}
        for line in order_items:
            key = ("format", line.format_id)
            if key not in requested:
                key = ("book", line.book_id)
            if key in ordered:
                return False
            ordered[key] = line.quantity
        return ordered == requested
