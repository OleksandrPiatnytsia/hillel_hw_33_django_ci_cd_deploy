"""The body of an event for Analytics: the order as it is now, without personal data.

The contract (version 1) is owned by Analytics: docs/events.md of
hillel_hw_34_django_analytics. In short:

    {"event_id": "...", "type": "order.paid", "version": 1,
     "occurred_at": "2026-11-18T10:15:00+00:00",
     "order": {"id": 42, "status": "processing", "payment_status": "paid",
               "created_at": "...", "currency": "USD", "total": "25.00",
               "total_uah": "1037.50", "customer_key": "<64 hex>",
               "items": [{"book": {"id": 7, "title": "...", "author": "...",
                                   "publisher": "", "language": "uk",
                                   "categories": [{"id": 3, "name": "Poetry"}]},
                          "format_type": "paper", "quantity": 2,
                          "price": "12.50", "amount_uah": "1037.50"}]}}

NOT sent: the name, phone, address and email of the customer, the user id.
Money: strings with 2 decimals, never floats (0.1 + 0.2 != 0.3).
"""

import hashlib
import hmac
from decimal import Decimal

from django.conf import settings

from books.models import BookFormat

CONTRACT_VERSION = 1
CENTS = Decimal("0.01")

# Our format values -> the values of the contract. Written out, not copied:
# a format added here later must not reach Analytics unnoticed (KeyError
# in the tests instead of a message that goes to the dead letters)
FORMAT_TYPES = {
    BookFormat.FormatType.PAPER: "paper",
    BookFormat.FormatType.EBOOK: "ebook",
    BookFormat.FormatType.AUDIOBOOK: "audio",
}


def money(value):
    """Decimal -> "12.50" (2 decimals, rounded half up as everywhere in the shop)."""
    return str(Decimal(value).quantize(CENTS))


def customer_key(user_id):
    """The same customer -> the same 64 hex characters; the user id can't be read back.

    HMAC-SHA256 with the secret CUSTOMER_KEY_SALT, not a plain sha256 of the
    id: without the secret nobody can try 1, 2, 3, ... and match the keys.
    Analytics needs only "the same buyer again or a new one".
    """
    return hmac.new(
        settings.CUSTOMER_KEY_SALT.encode(), str(user_id).encode(), hashlib.sha256
    ).hexdigest()


def book_snapshot(book):
    return {
        "id": book.pk,
        "title": book.title,
        "author": book.author.name,
        "publisher": book.publisher.name if book.publisher_id else "",
        "language": book.language,
        "categories": [
            {"id": category.pk, "name": category.name}
            for category in sorted(book.categories.all(), key=lambda category: category.pk)
        ],
    }


def order_snapshot(order):
    """The "order" part of the body. Reads the items with their books (4 queries)."""
    items = order.items.select_related("book__author", "book__publisher").prefetch_related(
        "book__categories"
    )
    return {
        "id": order.pk,
        "status": order.status,
        "payment_status": order.payment_status,
        "created_at": order.created_at.isoformat(),
        "currency": order.currency_id,
        "total": money(order.total),
        # The rate of the day of the order: the revenue in UAH doesn't change
        # when the rates change later (Order.exchange_rate)
        "total_uah": money(order.total_uah),
        "customer_key": customer_key(order.user_id),
        "items": [
            {
                "book": book_snapshot(item.book),
                "format_type": FORMAT_TYPES[item.format_type],
                "quantity": item.quantity,
                "price": money(item.price),
                "amount_uah": money(item.cost * order.exchange_rate),
            }
            for item in items.order_by("pk")
        ],
    }


def event_body(event_id, event_type, occurred_at, order):
    return {
        "event_id": str(event_id),
        "type": event_type,
        "version": CONTRACT_VERSION,
        "occurred_at": occurred_at.isoformat(),
        "order": order_snapshot(order),
    }
