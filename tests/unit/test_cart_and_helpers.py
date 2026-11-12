"""Unit tests of small building blocks: the session cart, the phone
normalizer, Stripe amounts, the --older-than parser."""

import argparse
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.sessions.backends.cached_db import SessionStore
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from cart.cart import CART_SESSION_KEY, Cart
from orders.management.commands.cancel_unpaid_orders import parse_age
from payments.providers.stripe_checkout import to_minor_units
from users.phone import normalize_phone

from ..factories import BookFactory


@pytest.fixture
def cart():
    """A Cart on a request with an empty (not saved) session."""
    request = RequestFactory().get("/")
    request.session = SessionStore()
    return Cart(request)


# ---------------------------------------------------------------------------
# cart.Cart
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cart_add_sums_quantities_and_override_sets_them(cart):
    book = BookFactory(stock=10)

    cart.add(book, quantity=2)
    cart.add(book, quantity=1)
    assert cart.quantity_of(book) == 3

    cart.add(book, quantity=1, override=True)
    assert cart.quantity_of(book) == 1


@pytest.mark.django_db
def test_cart_never_holds_more_than_stock(cart):
    book = BookFactory(stock=2)

    assert cart.add(book, quantity=5) == 2


@pytest.mark.django_db
def test_cart_book_out_of_stock_is_removed(cart):
    book = BookFactory(stock=0)

    assert cart.add(book) == 0
    assert not cart


@pytest.mark.django_db
def test_cart_len_total_and_quantities(cart):
    first = BookFactory(price=Decimal("100.00"))
    second = BookFactory(price=Decimal("50.50"))
    cart.add(first, quantity=2)
    cart.add(second, quantity=1)

    assert len(cart) == 3
    assert cart.total == Decimal("250.50")
    assert cart.quantities() == {first.pk: 2, second.pk: 1}
    # In the session: string keys (JSON), quantities only (no prices)
    assert cart.session[CART_SESSION_KEY] == {
        str(first.pk): {"quantity": 2},
        str(second.pk): {"quantity": 1},
    }


@pytest.mark.django_db
def test_cart_drops_a_book_deleted_after_it_was_added(cart):
    book = BookFactory()
    cart.add(book)
    book.delete()

    assert list(cart) == []
    assert cart.session[CART_SESSION_KEY] == {}


@pytest.mark.django_db
def test_cart_remove_and_clear(cart):
    first, second = BookFactory(), BookFactory()
    cart.add(first)
    cart.add(second)

    cart.remove(first)
    assert cart.quantities() == {second.pk: 1}

    cart.clear()
    assert CART_SESSION_KEY not in cart.session


# ---------------------------------------------------------------------------
# users.phone.normalize_phone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("+380 (67) 123-45-67", "+380671234567"),
        ("067 123 45 67", "0671234567"),
        ("   ", ""),
    ],
)
def test_normalize_phone_accepts_common_formats(value, expected):
    assert normalize_phone(value) == expected


@pytest.mark.parametrize("value", ["12345", "+380 67 abc 45 67", "1" * 16])
def test_normalize_phone_rejects_non_phones(value):
    with pytest.raises(ValidationError):
        normalize_phone(value)


# ---------------------------------------------------------------------------
# Stripe amounts, command arguments
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(Decimal("250.50"), 25050), (Decimal("0.01"), 1), ("99.999", 10000)],
)
def test_to_minor_units(amount, expected):
    assert to_minor_units(amount) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("30m", timedelta(minutes=30)), ("24H", timedelta(hours=24)), (" 2d ", timedelta(days=2))],
)
def test_parse_age(value, expected):
    assert parse_age(value) == expected


@pytest.mark.parametrize("value", ["0h", "10", "1w", "abc"])
def test_parse_age_rejects_wrong_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_age(value)
