"""Integration: managers in the admin, and the cancel_unpaid_orders command."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone

from orders.models import Order
from orders.services import create_order
from payments.admin import ManualPaymentFormSet
from payments.models import Payment

from ..factories import BookFactory, PaymentFactory
from ..helpers import admin_change_form_data, inline_prefix, message_levels

pytestmark = pytest.mark.django_db


@pytest.fixture
def book():
    return BookFactory(price=Decimal("100.00"), stock=10)


@pytest.fixture
def order(customer, book):
    """An order made by the real checkout code: 3 books reserved, 300 UAH."""
    return create_order(
        customer, {book.pk: 3}, full_name="Ann", phone="+380671234567", address="Kyiv"
    )


def change_url(order):
    return reverse("admin:orders_order_change", args=[order.pk])


# ---------------------------------------------------------------------------
# Who may open the orders in the admin
# ---------------------------------------------------------------------------


def test_manager_sees_orders_in_admin_customer_does_not(order, manager_client, customer_client):
    changelist = reverse("admin:orders_order_changelist")

    assert manager_client.get(changelist).status_code == 200
    assert manager_client.get(change_url(order)).status_code == 200
    # Not staff -> the admin login page
    response = customer_client.get(changelist)
    assert response.status_code == 302
    assert response.url.startswith(reverse("admin:login"))


def test_manager_cannot_add_or_delete_orders(order, manager_client):
    assert manager_client.get(reverse("admin:orders_order_add")).status_code == 403
    assert (
        manager_client.get(reverse("admin:orders_order_delete", args=[order.pk])).status_code == 403
    )


# ---------------------------------------------------------------------------
# Manual payments on the order page
# ---------------------------------------------------------------------------


def add_manual_payment(client, order, amount, note="cash"):
    page = client.get(change_url(order))
    data = admin_change_form_data(page)
    prefix = inline_prefix(page, ManualPaymentFormSet)
    data[f"{prefix}-TOTAL_FORMS"] = 1
    data[f"{prefix}-0-amount"] = amount
    data[f"{prefix}-0-note"] = note
    return client.post(change_url(order), data)


def test_manual_payments_in_parts_then_paid_with_one_email(
    order, manager_client, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        add_manual_payment(manager_client, order, "100.00")
    order.refresh_from_db()
    assert order.payment_status == Order.PaymentStatus.PARTIALLY_PAID
    assert mailoutbox == []  # no email for a part

    with django_capture_on_commit_callbacks(execute=True):
        response = add_manual_payment(manager_client, order, "200.00", note="bank transfer")

    assert response.status_code == 302  # saved, back to the list
    order.refresh_from_db()
    assert order.payment_status == Order.PaymentStatus.PAID
    payments = order.payments.order_by("created_at")
    assert [p.provider for p in payments] == [Payment.Provider.MANUAL] * 2
    assert payments.last().details == {"note": "bank transfer", "recorded_by": "manager"}
    assert len(mailoutbox) == 1


def test_manual_payment_above_amount_due_is_rejected(order, manager_client):
    response = add_manual_payment(manager_client, order, "999.00")

    assert response.status_code == 200  # the form again, with the error
    assert not order.payments.exists()


# ---------------------------------------------------------------------------
# Cancelling in the admin returns the books
# ---------------------------------------------------------------------------


def test_manager_cancels_order_by_status_field(order, book, manager_client):
    data = admin_change_form_data(manager_client.get(change_url(order)))
    data["status"] = Order.Status.CANCELLED

    manager_client.post(change_url(order), data)

    order.refresh_from_db()
    book.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert book.stock == 10


def test_cancel_action_warns_about_paid_orders(customer, book, manager_client):
    unpaid = create_order(
        customer, {book.pk: 1}, full_name="Ann", phone="+380671234567", address="Kyiv"
    )
    paid = create_order(
        customer, {book.pk: 2}, full_name="Ann", phone="+380671234567", address="Kyiv"
    )
    PaymentFactory(order=paid, status=Payment.Status.SUCCEEDED, amount=paid.total)
    paid.refresh_payment_status()

    response = manager_client.post(
        reverse("admin:orders_order_changelist"),
        {"action": "cancel_selected", "_selected_action": [unpaid.pk, paid.pk]},
        follow=True,
    )

    assert set(Order.objects.values_list("status", flat=True)) == {Order.Status.CANCELLED}
    book.refresh_from_db()
    assert book.stock == 10
    # Two "cancelled" + one "return the money" for the paid order
    assert sorted(message_levels(response)) == ["success", "success", "warning"]


# ---------------------------------------------------------------------------
# manage.py cancel_unpaid_orders
# ---------------------------------------------------------------------------


@pytest.fixture
def old_orders(customer, book):
    """Two orders from two days ago (one unpaid, one paid) and a fresh unpaid one."""

    def make(quantity):
        return create_order(
            customer, {book.pk: quantity}, full_name="Ann", phone="+380671234567", address="Kyiv"
        )

    old_unpaid, old_paid, fresh = make(1), make(2), make(3)
    PaymentFactory(order=old_paid, status=Payment.Status.SUCCEEDED, amount=old_paid.total)
    old_paid.refresh_payment_status()
    # created_at is auto_now_add: only update() can move it back in time
    Order.objects.filter(pk__in=[old_unpaid.pk, old_paid.pk]).update(
        created_at=timezone.now() - timedelta(days=2)
    )
    return old_unpaid, old_paid, fresh


def run_command(*args):
    out = StringIO()
    call_command("cancel_unpaid_orders", *args, stdout=out)
    return out.getvalue()


def test_cancel_unpaid_orders_cancels_only_old_unpaid(old_orders, book):
    old_unpaid, old_paid, fresh = old_orders

    output = run_command()

    statuses = dict(Order.objects.values_list("pk", "status"))
    assert statuses == {
        old_unpaid.pk: Order.Status.CANCELLED,
        old_paid.pk: Order.Status.NEW,
        fresh.pk: Order.Status.NEW,
    }
    book.refresh_from_db()
    assert book.stock == 10 - 2 - 3  # the old unpaid copy is back
    assert f"#{old_unpaid.pk}" in output


def test_cancel_unpaid_orders_dry_run_changes_nothing(old_orders, book):
    old_unpaid, _, _ = old_orders

    output = run_command("--dry-run")

    assert f"#{old_unpaid.pk}" in output
    assert not Order.objects.filter(status=Order.Status.CANCELLED).exists()
    book.refresh_from_db()
    assert book.stock == 10 - 1 - 2 - 3


def test_cancel_unpaid_orders_refuses_too_short_age():
    with pytest.raises(CommandError):
        run_command("--older-than", "10m")


# ---------------------------------------------------------------------------
# seed_books and book_stats
# ---------------------------------------------------------------------------


def test_seed_books_fills_the_catalog_and_is_safe_to_run_again():
    from books.models import Author, Book, Category

    call_command("seed_books", stdout=StringIO())
    counts = (Category.objects.count(), Author.objects.count(), Book.objects.count())
    call_command("seed_books", stdout=StringIO())  # the second run adds nothing

    assert counts == (5, 10, 12)  # Tolkien and King have two books each
    assert (Category.objects.count(), Author.objects.count(), Book.objects.count()) == counts
    assert Book.objects.get(title="Хоббіт").categories.count() == 2


def test_book_stats_prints_every_section_and_sql_on_request():
    call_command("seed_books", stdout=StringIO())
    out = StringIO()

    call_command("book_stats", "--max-price", "150", "--search", "Кінг", "--sql", stdout=out)

    output = out.getvalue()
    assert "Вбивство в «Східному експресі»" in output  # 140 UAH, in stock: price <= 150
    assert "Собака Баскервілів" in output  # stock 0: the "out of stock" section
    assert "Воно" in output and "Сяйво" in output  # found by the author "Кінг"
    assert "aggregate: whole store" in output
    assert "SQL: SELECT" in output


def test_book_stats_on_an_empty_catalog():
    out = StringIO()

    call_command("book_stats", stdout=out)

    assert "(nothing found)" in out.getvalue()


# ---------------------------------------------------------------------------
# Books and stock in the admin (stock in inventory.Stock since hw_31)
# ---------------------------------------------------------------------------


# Generated with AI
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # o=5: the 5th column of list_display ("stock"), ascending
        ("?o=5", ["Out", "Few", "Plenty"]),
        ("?o=-5", ["Plenty", "Few", "Out"]),
        ("?stock_status=low", ["Few"]),
        ("?stock_status=out", ["Out"]),
    ],
)
def test_admin_book_list_sorts_and_filters_by_stock(manager_client, query, expected):
    BookFactory(title="Plenty", stock=50)
    BookFactory(title="Few", stock=2)
    BookFactory(title="Out", stock=0)

    response = manager_client.get(reverse("admin:books_book_changelist") + query)

    assert response.status_code == 200
    assert [book.title for book in response.context["cl"].result_list] == expected


# Generated with AI
def test_admin_book_page_shows_the_stock_inline_and_stock_list(manager_client, book):
    page = manager_client.get(reverse("admin:books_book_change", args=[book.pk]))
    stock_list = manager_client.get(reverse("admin:inventory_stock_changelist"))

    assert page.status_code == 200
    assert "stocks-TOTAL_FORMS" in page.content.decode()
    assert stock_list.status_code == 200
    assert [stock.quantity for stock in stock_list.context["cl"].result_list] == [10]
