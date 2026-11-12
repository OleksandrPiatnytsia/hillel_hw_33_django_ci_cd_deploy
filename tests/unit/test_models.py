"""Unit tests of the models: properties, save() rules, database constraints.

@pytest.mark.parametrize runs one test function with several inputs:
every tuple is a separate test in the report (test_x[in_stock], ...).

Every test is marked "# Generated with AI, reviewed and modified": the
first versions were written by Claude (Claude Code), then checked and
changed by hand (see AI_PROMPTS.md).
"""

from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import translation

from books.models import Book, BookCategory, BookQuerySet
from orders.models import Order
from payments.models import Payment
from users.models import User

from ..factories import (
    AuthorFactory,
    BookFactory,
    CategoryFactory,
    OrderFactory,
    OrderItemFactory,
    PaymentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db  # every test in this file uses the database


# ---------------------------------------------------------------------------
# users.User
# ---------------------------------------------------------------------------


# Generated with AI, reviewed and modified
def test_user_email_is_saved_in_lowercase():
    user = User.objects.create_user("ann", email="Ann.Shevchenko@Mail.COM", password="x")

    user.refresh_from_db()
    assert user.email == "ann.shevchenko@mail.com"


# Generated with AI, reviewed and modified
def test_user_email_lowercase_constraint_protects_update():
    """QuerySet.update() skips save(): the database CHECK constraint stops it."""
    user = UserFactory()

    with pytest.raises(IntegrityError):
        User.objects.filter(pk=user.pk).update(email="UPPER@EXAMPLE.COM")


# ---------------------------------------------------------------------------
# books.Book
# ---------------------------------------------------------------------------


# Generated with AI, reviewed and modified
@pytest.mark.parametrize(
    ("stock", "expected"),
    [(0, False), (1, True), (5, True), (6, False)],
)
def test_book_is_low_stock(stock, expected):
    # build(): an object in memory only, a property needs no database
    assert BookFactory.build(stock=stock).is_low_stock is expected


# Generated with AI, reviewed and modified
def test_book_without_cover_uses_placeholder():
    assert BookFactory.build(cover="").cover_url.endswith("img/no-cover.svg")


# Generated with AI, reviewed and modified
def test_book_str_has_title_and_author():
    book = BookFactory(title="Kobzar", author__name="Taras Shevchenko")

    assert str(book) == "Kobzar — Taras Shevchenko"


# Generated with AI, reviewed and modified
@pytest.mark.parametrize(
    ("status", "expected_titles"),
    [
        (BookQuerySet.STOCK_IN, {"low", "plenty"}),
        (BookQuerySet.STOCK_LOW, {"low"}),
        (BookQuerySet.STOCK_OUT, {"none"}),
        ("", {"none", "low", "plenty"}),  # empty / unknown -> no filter
    ],
)
def test_books_by_stock_status(status, expected_titles):
    BookFactory(title="none", stock=0)
    BookFactory(title="low", stock=3)
    BookFactory(title="plenty", stock=50)

    titles = set(Book.objects.by_stock_status(status).values_list("title", flat=True))

    assert titles == expected_titles


# Generated with AI, reviewed and modified
def test_book_with_uploaded_cover_uses_its_url():
    # The other branch of cover_url: a file name is enough, the file itself
    # is not read (FieldFile.url = MEDIA_URL + name)
    assert BookFactory.build(cover="covers/kobzar.jpg").cover_url.endswith("/covers/kobzar.jpg")


# ---------------------------------------------------------------------------
# orders.Order / OrderItem
# ---------------------------------------------------------------------------


# Generated with AI, reviewed and modified
def test_order_item_cost_is_price_times_quantity():
    item = OrderItemFactory(book__price=Decimal("120.50"), quantity=3)

    assert item.cost == Decimal("361.50")


# Generated with AI, reviewed and modified
def test_order_item_quantity_zero_is_rejected_by_database():
    with pytest.raises(IntegrityError):
        OrderItemFactory(quantity=0)


# Generated with AI, reviewed and modified
@pytest.mark.parametrize(
    ("paid", "expected_status", "expected_percent"),
    [
        ([], Order.PaymentStatus.UNPAID, 0),
        (["100.00"], Order.PaymentStatus.PARTIALLY_PAID, 40),
        (["100.00", "150.00"], Order.PaymentStatus.PAID, 100),
    ],
)
def test_order_payment_status_follows_succeeded_payments(paid, expected_status, expected_percent):
    order = OrderFactory(total=Decimal("250.00"))
    for amount in paid:
        PaymentFactory(order=order, amount=Decimal(amount), status=Payment.Status.SUCCEEDED)
    # A pending payment never counts
    PaymentFactory(order=order, amount=Decimal("250.00"), status=Payment.Status.PENDING)

    order.refresh_payment_status()

    order.refresh_from_db()
    assert order.payment_status == expected_status
    assert order.paid_percent == expected_percent
    assert order.amount_due == Decimal("250.00") - sum(Decimal(a) for a in paid)


# Generated with AI, reviewed and modified
def test_order_refresh_payment_status_reports_no_change():
    order = OrderFactory(total=Decimal("250.00"))

    assert order.refresh_payment_status() is False  # unpaid -> unpaid


# Generated with AI, reviewed and modified
@pytest.mark.parametrize(
    ("status", "payment_status", "expected"),
    [
        (Order.Status.NEW, Order.PaymentStatus.UNPAID, True),
        (Order.Status.NEW, Order.PaymentStatus.PARTIALLY_PAID, False),
        (Order.Status.PROCESSING, Order.PaymentStatus.UNPAID, False),
        (Order.Status.CANCELLED, Order.PaymentStatus.UNPAID, False),
    ],
)
def test_order_can_be_cancelled_by_customer(status, payment_status, expected):
    order = OrderFactory.build(status=status, payment_status=payment_status)

    assert order.can_be_cancelled_by_customer is expected


# Generated with AI, reviewed and modified
def test_order_with_zero_total_counts_as_fully_paid():
    """paid_percent must not divide by zero: a free order is 100% paid."""
    assert OrderFactory.build(total=Decimal("0.00")).paid_percent == 100


# ---------------------------------------------------------------------------
# payments.Payment
# ---------------------------------------------------------------------------


# Generated with AI, reviewed and modified
def test_payment_same_stripe_session_cannot_be_saved_twice():
    PaymentFactory(external_id="cs_test_same")

    with pytest.raises(IntegrityError):
        PaymentFactory(external_id="cs_test_same")


# Generated with AI, reviewed and modified
def test_two_manual_payments_without_external_id_are_allowed():
    order = OrderFactory(total=Decimal("250.00"))
    PaymentFactory(order=order, provider=Payment.Provider.MANUAL, external_id="", amount=10)
    PaymentFactory(order=order, provider=Payment.Provider.MANUAL, external_id="", amount=20)

    assert order.payments.count() == 2


# ---------------------------------------------------------------------------
# __str__ and get_absolute_url of all the models
# ---------------------------------------------------------------------------


# Generated with AI, reviewed and modified
def test_models_str_and_urls():
    """What the admin, the messages and the emails show, and the page links."""
    poetry = CategoryFactory(name="Poetry")
    author = AuthorFactory(name="Taras Shevchenko")
    book = BookFactory(title="Kobzar", author=author, categories=[poetry])
    order = OrderFactory(total=Decimal("250.00"))
    item = OrderItemFactory(order=order, title="Kobzar", quantity=2)
    payment = PaymentFactory(
        order=order,
        provider=Payment.Provider.MANUAL,
        external_id="",
        amount=Decimal("250.00"),
        status=Payment.Status.SUCCEEDED,
    )

    # English: Order and Payment translate their __str__ (gettext)
    with translation.override("en"):
        assert str(order) == f"Order #{order.pk}"
        assert str(payment) == f"Manual 250.00 UAH (Succeeded) for order #{order.pk}"
    assert str(poetry) == "Poetry"
    assert str(author) == "Taras Shevchenko"
    assert str(BookCategory.objects.get(book=book)) == "Kobzar → Poetry"
    assert str(item) == "Kobzar × 2"

    assert book.get_absolute_url() == f"/{book.pk}/"  # the catalog is at the site root
    assert author.get_absolute_url() == f"/authors/{author.pk}/"
    assert order.get_absolute_url() == f"/orders/{order.pk}/"
