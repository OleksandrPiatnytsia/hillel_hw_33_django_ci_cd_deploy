"""Celery tasks: emails with retries, the periodic tasks, the low stock report.

CELERY_TASK_ALWAYS_EAGER=True in config/settings/test.py: task.delay()
runs the task here, at once, with its retries (without the pauses).
"""

import csv
import io
import logging
import smtplib
from datetime import date, timedelta

import pytest
from django.contrib.sessions.models import Session
from django.core.mail import EmailMessage
from django.utils import timezone
from kombu.exceptions import OperationalError

from config.celery import app as celery_app
from orders.models import Order
from orders.reports import build_low_stock_report
from orders.services import cancel_order, create_order
from orders.tasks import (
    cancel_unpaid_orders,
    send_low_stock_report,
    send_order_created_email_task,
)
from users.tasks import clear_expired_sessions

from ..factories import BookFactory, OrderFactory, UserFactory
from ..helpers import format_id

pytestmark = pytest.mark.django_db

DELIVERY = {"full_name": "Ann", "phone": "+380671234567", "address": "Kyiv"}


@pytest.fixture
def send_attempts(monkeypatch):
    """Every email fails like Gmail being down; returns the list of attempts."""
    attempts = []

    def broken_send(self, fail_silently=False):
        attempts.append(self.subject)
        raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed (test)")

    monkeypatch.setattr(EmailMessage, "send", broken_send)
    return attempts


# ---------------------------------------------------------------------------
# Emails as tasks
# ---------------------------------------------------------------------------


# Generated with AI
def test_order_email_is_sent_by_the_task_after_commit(
    customer, mailoutbox, django_capture_on_commit_callbacks
):
    book = BookFactory()  # outside: its cache invalidation is an on_commit too
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        order = create_order(customer, {format_id(book): 1}, **DELIVERY)

    # The email task is queued only after COMMIT: nothing sent before it.
    # The other callback: the outbox publisher for Analytics (outbox.services)
    assert [callback.__qualname__ for callback in callbacks] == [
        "_publish_soon",
        "enqueue_on_commit.<locals>.send",
    ]
    assert [message.to for message in mailoutbox] == [[customer.email]]
    assert f"#{order.pk}" in mailoutbox[0].subject


# Generated with AI
def test_failed_email_is_retried_three_times(send_attempts):
    order = OrderFactory(items=[(BookFactory(), 1)])

    result = send_order_created_email_task.delay(order.pk)

    assert len(send_attempts) == 1 + 3  # the first try + 3 retries
    assert result.failed()


# Generated with AI
def test_email_of_a_missing_order_is_not_retried(send_attempts):
    result = send_order_created_email_task.delay(999999)

    # Order.DoesNotExist is not an OSError: no retry, the task fails at once
    assert result.failed()
    assert send_attempts == []


# Generated with AI
def test_broker_down_runs_the_task_here(
    customer, mailoutbox, monkeypatch, django_capture_on_commit_callbacks
):
    def no_broker(*args, **kwargs):
        raise OperationalError("Error 111 connecting to redis:6379. Connection refused.")

    monkeypatch.setattr(send_order_created_email_task, "delay", no_broker)

    with django_capture_on_commit_callbacks(execute=True):
        create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)

    assert len(mailoutbox) == 1  # sent synchronously instead


# ---------------------------------------------------------------------------
# Periodic tasks (Celery Beat)
# ---------------------------------------------------------------------------


# Generated with AI
def test_every_task_of_the_beat_schedule_exists(settings):
    for entry in settings.CELERY_BEAT_SCHEDULE.values():
        assert entry["task"] in celery_app.tasks


# Generated with AI
def test_cancel_unpaid_orders_task_cancels_only_old_orders(customer, settings):
    settings.ORDER_UNPAID_MAX_AGE_HOURS = 24
    book = BookFactory(stock=10)
    old = create_order(customer, {format_id(book): 2}, **DELIVERY)
    new = create_order(customer, {format_id(book): 3}, **DELIVERY)
    Order.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=25))

    cancel_unpaid_orders.delay()

    old.refresh_from_db()
    new.refresh_from_db()
    book.refresh_from_db()
    assert (old.status, new.status) == (Order.Status.CANCELLED, Order.Status.NEW)
    assert book.stock == 10 - 3  # the 2 copies of the old order are back


# Generated with AI
def test_automatic_cancellation_emails_the_customer(
    customer, settings, mailoutbox, django_capture_on_commit_callbacks
):
    settings.ORDER_UNPAID_MAX_AGE_HOURS = 24
    book = BookFactory(title="Kobzar")
    order = create_order(customer, {format_id(book): 2}, **DELIVERY)
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=25))

    with django_capture_on_commit_callbacks(execute=True):
        cancel_unpaid_orders.delay()

    assert [message.to for message in mailoutbox] == [[customer.email]]
    message = mailoutbox[0]
    assert f"#{order.pk}" in message.subject
    assert "Kobzar" in message.body
    assert "Kobzar" in message.alternatives[0].content  # the HTML part


# Generated with AI
def test_cancel_unpaid_orders_logs_every_run_even_with_nothing_to_cancel(caplog):
    with caplog.at_level(logging.INFO, logger="orders"):
        cancel_unpaid_orders.delay()

    assert "Unpaid orders older than 1 day, 0:00:00: cancelled 0, skipped 0" in caplog.text


# Generated with AI
def test_order_paid_while_the_command_runs_is_skipped(customer, monkeypatch, mailoutbox, caplog):
    """The payment comes between the SELECT of old orders and the cancel."""
    from orders.management.commands import cancel_unpaid_orders as command

    order = create_order(customer, {format_id(BookFactory(stock=5)): 1}, **DELIVERY)
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=25))
    real_cancel_order = command.cancel_order

    def paid_just_now(order_id, **kwargs):
        Order.objects.filter(pk=order_id).update(payment_status=Order.PaymentStatus.PAID)
        return real_cancel_order(order_id, **kwargs)

    monkeypatch.setattr(command, "cancel_order", paid_just_now)

    with caplog.at_level(logging.INFO, logger="orders"):
        cancel_unpaid_orders.delay()

    order.refresh_from_db()
    assert order.status == Order.Status.NEW  # the payment wins
    assert "cancelled 0, skipped 1" in caplog.text
    assert mailoutbox == []


# Generated with AI
def test_customer_cancelling_own_order_gets_no_cancellation_email(
    customer, mailoutbox, django_capture_on_commit_callbacks
):
    book = BookFactory()
    order = create_order(customer, {format_id(book): 1}, **DELIVERY)

    with django_capture_on_commit_callbacks(execute=True):
        cancel_order(order.pk, user=customer)

    assert mailoutbox == []  # the customer pressed "Cancel" and knows


# Generated with AI
def test_clear_expired_sessions_deletes_only_expired_ones():
    now = timezone.now()
    Session.objects.create(session_key="old", session_data="x", expire_date=now - timedelta(days=1))
    Session.objects.create(
        session_key="live", session_data="x", expire_date=now + timedelta(days=1)
    )

    clear_expired_sessions.delay()

    assert list(Session.objects.values_list("session_key", flat=True)) == ["live"]


# ---------------------------------------------------------------------------
# The low stock report (the sales are in the daily email of Analytics)
# ---------------------------------------------------------------------------


@pytest.fixture
def low_stock_books():
    kobzar = BookFactory(title="Kobzar", stock=3)
    empty = BookFactory(title="Aeneid", stock=0)
    BookFactory(title="Zakhar Berkut", stock=40)  # enough
    BookFactory(title="E-book", format_type="ebook", formats=True)  # no copies at all
    return kobzar, empty


def read_csv(content):
    # Django turns a text/* attachment into str; the BOM stays at the start
    assert content.startswith("\ufeff")
    return list(csv.reader(io.StringIO(content.removeprefix("\ufeff"))))


# Generated with AI
def test_low_stock_report_lists_paper_books_with_few_copies(low_stock_books):
    report = build_low_stock_report()

    # The emptiest first
    assert [(book.title, book.stock) for book in report.books] == [("Aeneid", 0), ("Kobzar", 3)]
    assert report.day == timezone.localdate()


# Generated with AI
def test_low_stock_report_is_emailed_to_managers_with_a_csv_file(
    low_stock_books, manager, mailoutbox, monkeypatch
):
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 11, 25))
    UserFactory(groups=["Customers"])  # not a recipient

    send_low_stock_report.delay()

    assert len(mailoutbox) == 1
    message = mailoutbox[0]
    assert message.bcc == [manager.email]
    assert message.to == []  # the managers don't see each other's addresses
    assert "25.11.2026" in message.subject
    files = {name: read_csv(content) for name, content, _type in message.attachments}
    assert list(files) == ["low_stock_2026-11-25.csv"]
    rows = files["low_stock_2026-11-25.csv"]
    assert rows[0] == ["book_id", "title", "author", "stock"]
    assert [row[1:2] + row[3:] for row in rows[1:]] == [["Aeneid", "0"], ["Kobzar", "3"]]
    # No sales any more: no orders, no customers' emails
    assert "Kobzar" in message.body
    assert "http://analytics.example/" in message.body


# Generated with AI
def test_low_stock_report_is_not_sent_when_nothing_runs_out(manager, mailoutbox):
    BookFactory(stock=40)

    assert send_low_stock_report.apply().get() == 0
    assert mailoutbox == []


# Generated with AI
def test_low_stock_report_without_managers_sends_nothing(low_stock_books, mailoutbox):
    assert send_low_stock_report.apply().get() == 0
    assert mailoutbox == []


# Generated with AI
def test_low_stock_report_without_analytics_has_no_analytics_line(
    low_stock_books, manager, mailoutbox, settings
):
    settings.ANALYTICS_PUBLIC_URL = ""

    send_low_stock_report.delay()

    assert "Analytics" not in mailoutbox[0].body
