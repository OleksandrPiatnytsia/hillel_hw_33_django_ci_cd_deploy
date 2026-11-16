"""Unit tests of small building blocks: the session cart, the phone
normalizer, Stripe amounts, the --older-than parser."""

import argparse
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.sessions.backends.cached_db import SessionStore
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from books.models import BookFormat
from cart.cart import CART_SESSION_KEY, OLD_CART_SESSION_KEY, Cart
from orders.management.commands.cancel_unpaid_orders import parse_age
from payments.providers.stripe_checkout import to_minor_units
from users.phone import normalize_phone

from ..factories import BookFactory, BookFormatFactory


@pytest.fixture
def cart():
    """A Cart on a request with an empty (not saved) session."""
    request = RequestFactory().get("/")
    request.session = SessionStore()
    return Cart(request)


# ---------------------------------------------------------------------------
# cart.Cart
# ---------------------------------------------------------------------------


def paper(book):
    """The format of a BookFactory book (paper), with its stock read fresh."""
    return BookFormat.objects.with_stock().get(book=book, format_type="paper")


@pytest.mark.django_db
def test_cart_add_sums_quantities_and_override_sets_them(cart):
    book_format = paper(BookFactory(stock=10))

    cart.add(book_format, quantity=2)
    cart.add(book_format, quantity=1)
    assert cart.quantity_of(book_format) == 3

    cart.add(book_format, quantity=1, override=True)
    assert cart.quantity_of(book_format) == 1


@pytest.mark.django_db
def test_cart_never_holds_more_than_stock(cart):
    assert cart.add(paper(BookFactory(stock=2)), quantity=5) == 2


@pytest.mark.django_db
def test_cart_book_out_of_stock_is_removed(cart):
    assert cart.add(paper(BookFactory(stock=0))) == 0
    assert not cart


@pytest.mark.django_db
def test_cart_ebook_has_no_stock_limit_and_a_format_not_on_sale_is_refused(cart):
    book = BookFactory(stock=0)
    ebook = BookFormatFactory(book=book, format_type="ebook")
    off = BookFormatFactory(book=book, format_type="audiobook", is_active=False)

    assert cart.add(ebook, quantity=50) == 50
    assert cart.add(off) == 0
    assert cart.quantities() == {ebook.pk: 50}


@pytest.mark.django_db
def test_cart_len_total_and_quantities(cart):
    first = paper(BookFactory(price=Decimal("100.00")))
    second = paper(BookFactory(price=Decimal("50.50")))
    cart.add(first, quantity=2)
    cart.add(second, quantity=1)

    assert len(cart) == 3
    assert cart.total == Decimal("250.50")
    assert cart.quantities() == {first.pk: 2, second.pk: 1}
    # In the session: string keys (JSON) of the formats, quantities only (no prices)
    assert cart.session[CART_SESSION_KEY] == {
        str(first.pk): {"quantity": 2},
        str(second.pk): {"quantity": 1},
    }


@pytest.mark.django_db
def test_cart_same_book_in_two_formats_is_two_lines(cart):
    book = BookFactory(price=Decimal("300.00"))
    ebook = BookFormatFactory(book=book, format_type="ebook", price=Decimal("120.00"))
    cart.add(paper(book))
    cart.add(ebook, quantity=2)

    items = {item["format"].format_type: item for item in cart}
    assert (items["paper"]["cost"], items["ebook"]["cost"]) == (
        Decimal("300.00"),
        Decimal("240.00"),
    )
    assert cart.total == Decimal("540.00")
    assert cart.lines_of(book) == [(paper(book), 1), (ebook, 2)]


@pytest.mark.django_db
def test_cart_change_format_moves_the_quantity_and_merges_lines(cart):
    book = BookFactory(stock=10)
    paper_format = paper(book)
    ebook = BookFormatFactory(book=book, format_type="ebook")
    cart.add(paper_format, quantity=2)

    assert cart.change_format(paper_format, ebook) == 2
    assert cart.quantities() == {ebook.pk: 2}

    cart.add(paper_format, quantity=1)
    # Back to paper: the two lines become one, 1 + 2
    assert cart.change_format(ebook, paper_format) == 3
    assert cart.quantities() == {paper_format.pk: 3}


@pytest.mark.django_db
def test_cart_change_to_a_sold_out_paper_book_keeps_the_line(cart):
    book = BookFactory(stock=0)
    ebook = BookFormatFactory(book=book, format_type="ebook")
    cart.add(ebook, quantity=2)

    assert cart.change_format(ebook, paper(book)) == 0
    assert cart.quantities() == {ebook.pk: 2}


@pytest.mark.django_db
def test_cart_line_switched_off_after_adding_is_marked_and_offers_the_others(cart):
    book = BookFactory()
    ebook = BookFormatFactory(book=book, format_type="ebook")
    cart.add(ebook)
    BookFormat.objects.filter(pk=ebook.pk).update(is_active=False)

    (item,) = list(cart)
    assert item["not_on_sale"] is True
    # The current format first (it stays selected), then the ones on sale
    assert item["format_choices"] == [ebook, paper(book)]


@pytest.mark.django_db
def test_cart_drops_a_format_deleted_after_it_was_added(cart):
    book = BookFactory()
    cart.add(paper(book))
    book.delete()

    assert list(cart) == []
    assert cart.session[CART_SESSION_KEY] == {}


@pytest.mark.django_db
def test_cart_remove_and_clear(cart):
    first, second = paper(BookFactory()), paper(BookFactory())
    cart.add(first)
    cart.add(second)

    cart.remove(first)
    assert cart.quantities() == {second.pk: 1}

    cart.clear()
    assert CART_SESSION_KEY not in cart.session


@pytest.mark.django_db
def test_old_cart_by_book_is_converted_to_the_main_formats_once():
    """A session of the release before: {"<book_id>": {"quantity": n}} under "cart"."""
    in_stock = BookFactory(stock=5)
    sold_out = BookFactory(stock=0)
    sold_out_ebook = BookFormatFactory(book=sold_out, format_type="ebook")
    not_on_sale = BookFactory(formats=False)
    request = RequestFactory().get("/")
    request.session = SessionStore()
    request.session[OLD_CART_SESSION_KEY] = {
        str(in_stock.pk): {"quantity": 2},
        # Paper sold out: the e-book that can be bought
        str(sold_out.pk): {"quantity": 1},
        # No format on sale, a deleted book: dropped
        str(not_on_sale.pk): {"quantity": 1},
        "999999": {"quantity": 1},
    }

    cart = Cart(request)

    assert cart.quantities() == {paper(in_stock).pk: 2, sold_out_ebook.pk: 1}
    assert OLD_CART_SESSION_KEY not in request.session
    # The next request reads only the new key
    assert Cart(request).quantities() == cart.quantities()


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
