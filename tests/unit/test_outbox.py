"""The outbox: events of the orders for Analytics (app outbox).

RabbitMQ is kombu's memory transport here (config/settings/test.py,
RABBITMQ_URL = "memory://"): the `analytics_queue` fixture binds a queue to
the exchange, like Analytics does, and reads what was published.
"""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from kombu import Connection, Queue
from kombu.messaging import Producer

from orders.services import OrderError, cancel_order, create_order
from outbox.models import OutboxEvent
from outbox.publisher import events_exchange, publish_pending
from outbox.snapshot import customer_key, order_snapshot
from outbox.tasks import delete_old_events, publish_pending_events
from payments.services import record_manual_payment

from ..factories import (
    BookFactory,
    BookFormatFactory,
    CategoryFactory,
    OrderFactory,
    UserFactory,
)

DELIVERY = {"full_name": "Ann Shevchenko", "phone": "+380671234567", "address": "Kyiv, Main 1"}


def format_id(book):
    return book.formats.get().pk


def events(event_type=None):
    queryset = OutboxEvent.objects.all()
    if event_type:
        queryset = queryset.filter(type=event_type)
    return list(queryset)


@pytest.fixture
def analytics_queue():
    """A queue bound to bookstore.events with "order.*"; returns a reader of its messages."""
    with Connection("memory://") as connection:
        queue = Queue("test.analytics.events", exchange=events_exchange(), routing_key="order.*")
        bound = queue(connection.default_channel)
        bound.declare()
        bound.purge()

        def received():
            messages = []
            while (message := bound.get(no_ack=True)) is not None:
                messages.append(message)
            return messages

        yield received
        bound.delete()


# ---------------------------------------------------------------------------
# Which changes of an order write an event
# ---------------------------------------------------------------------------


def test_create_order_writes_order_created(customer):
    book = BookFactory(price="120.00")

    order = create_order(customer, {format_id(book): 2}, **DELIVERY)

    [event] = events()
    assert event.type == OutboxEvent.Type.ORDER_CREATED
    assert event.order_id == order.pk
    body = event.payload
    assert body["event_id"] == str(event.event_id)
    assert body["type"] == "order.created"
    assert body["version"] == 1
    assert body["order"]["status"] == "new"
    assert body["order"]["payment_status"] == "unpaid"
    assert body["order"]["total"] == "240.00"
    [item] = body["order"]["items"]
    assert item["quantity"] == 2
    assert item["price"] == "120.00"
    assert item["amount_uah"] == "240.00"


def test_failed_order_writes_no_event(customer):
    """Not enough copies: the transaction is rolled back, the event with it."""
    book = BookFactory(stock=1)

    with pytest.raises(OrderError):
        create_order(customer, {format_id(book): 5}, **DELIVERY)

    assert events() == []


def test_rolled_back_transaction_takes_the_event_away(customer):
    book = BookFactory()

    with pytest.raises(RuntimeError), transaction.atomic():
        create_order(customer, {format_id(book): 1}, **DELIVERY)
        raise RuntimeError("something later in the same transaction failed")

    assert events() == []


def test_cancel_order_writes_order_cancelled(customer):
    order = create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)

    cancel_order(order.pk, user=customer)

    [event] = events(OutboxEvent.Type.ORDER_CANCELLED)
    assert event.payload["order"]["status"] == "cancelled"


def test_full_payment_writes_order_paid(customer):
    order = create_order(customer, {format_id(BookFactory(price="100.00")): 1}, **DELIVERY)

    record_manual_payment(order.pk, "100.00")

    [event] = events(OutboxEvent.Type.ORDER_PAID)
    assert event.payload["order"]["payment_status"] == "paid"


def test_part_payment_writes_no_event_until_the_order_is_paid(customer):
    """The contract has no event for a part payment."""
    order = create_order(customer, {format_id(BookFactory(price="100.00")): 1}, **DELIVERY)

    record_manual_payment(order.pk, "40.00")
    assert events(OutboxEvent.Type.ORDER_PAID) == []

    record_manual_payment(order.pk, "60.00")
    assert len(events(OutboxEvent.Type.ORDER_PAID)) == 1


# ---------------------------------------------------------------------------
# The snapshot (the contract of Analytics, docs/events.md)
# ---------------------------------------------------------------------------


def test_snapshot_has_no_personal_data(customer):
    order = create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)

    text = json.dumps(OutboxEvent.objects.get().payload)

    for private in [customer.email, customer.username, *DELIVERY.values()]:
        assert private not in text
    assert set(OutboxEvent.objects.get().payload["order"]) == {
        "id",
        "status",
        "payment_status",
        "created_at",
        "currency",
        "total",
        "total_uah",
        "customer_key",
        "items",
    }
    assert order.pk == OutboxEvent.objects.get().payload["order"]["id"]


def test_snapshot_of_a_foreign_currency_order_has_amounts_in_uah(db):
    """total * exchange_rate = UAH, at the rate of the day of the order."""
    poetry = CategoryFactory(name="Poetry")
    book = BookFactory(
        title="Kobzar", language="uk", categories=[poetry], price="12.50", currency_id="USD"
    )
    order = OrderFactory(currency_id="USD", exchange_rate=Decimal("41.5"), items=[(book, 2)])

    snapshot = order_snapshot(order)

    assert snapshot["currency"] == "USD"
    assert snapshot["total"] == "25.00"
    assert snapshot["total_uah"] == "1037.50"
    [item] = snapshot["items"]
    assert item["amount_uah"] == "1037.50"
    assert item["book"] == {
        "id": book.pk,
        "title": "Kobzar",
        "author": book.author.name,
        "publisher": "",
        "language": "uk",
        "categories": [{"id": poetry.pk, "name": "Poetry"}],
    }


def test_audiobook_is_audio_in_the_contract(db):
    book = BookFactory(formats=False)
    audiobook = BookFormatFactory(book=book, format_type="audiobook")
    order = OrderFactory(items=[(audiobook, 1)])

    [item] = order_snapshot(order)["items"]

    assert item["format_type"] == "audio"


def test_customer_key_is_stable_and_secret(settings):
    key = customer_key(5)

    assert len(key) == 64 and int(key, 16) >= 0  # 64 hex characters
    assert customer_key(5) == key
    assert customer_key(6) != key
    # Another salt -> another key: without the salt the id can't be matched
    settings.CUSTOMER_KEY_SALT = "another-salt"
    assert customer_key(5) != key


# ---------------------------------------------------------------------------
# Sending to RabbitMQ
# ---------------------------------------------------------------------------


def test_event_is_sent_after_the_commit(
    customer, analytics_queue, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        order = create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)

    [message] = analytics_queue()
    event = OutboxEvent.objects.get()
    assert event.published_at is not None
    assert message.delivery_info["routing_key"] == "order.created"
    assert message.properties["message_id"] == str(event.event_id)
    assert message.content_type == "application/json"
    assert json.loads(message.body)["order"]["id"] == order.pk


def test_nothing_is_sent_before_the_commit(customer, analytics_queue):
    # Without executing the on_commit callbacks (the test transaction never commits)
    create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)

    assert analytics_queue() == []
    assert OutboxEvent.objects.get().published_at is None


def test_events_are_sent_oldest_first_and_only_once(customer, analytics_queue):
    order = create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)
    cancel_order(order.pk)

    assert publish_pending() == 2
    assert publish_pending() == 0  # sent rows are not sent again

    keys = [message.delivery_info["routing_key"] for message in analytics_queue()]
    assert keys == ["order.created", "order.cancelled"]


def test_without_rabbitmq_the_events_wait(customer, settings, analytics_queue):
    """Railway before Analytics: RABBITMQ_URL = "" -> nothing sent, no error."""
    settings.RABBITMQ_URL = ""
    create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)

    assert publish_pending() == 0
    assert OutboxEvent.objects.get().published_at is None
    assert analytics_queue() == []


def test_rabbitmq_down_keeps_the_events_and_records_the_error(customer, settings, caplog):
    order = create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)
    cancel_order(order.pk)
    # Nothing listens on port 1: "connection refused" at once
    settings.RABBITMQ_URL = "amqp://guest:guest@127.0.0.1:1//"

    assert publish_pending() == 0

    first, second = events()
    assert first.published_at is None and second.published_at is None
    assert first.failed_attempts == 1 and first.last_error
    # The run stopped at the first one: the later event wasn't even tried
    assert second.failed_attempts == 0
    assert "not sent" in caplog.text


def test_message_without_a_queue_stays_unsent(customer, monkeypatch):
    """RabbitMQ returns a mandatory message no queue is bound for (Analytics never started)."""

    def returned_by_rabbitmq(producer, body, routing_key, **options):
        producer.on_return(None, "bookstore.events", routing_key, None)

    monkeypatch.setattr(Producer, "publish", returned_by_rabbitmq)
    create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)

    assert publish_pending() == 0

    event = OutboxEvent.objects.get()
    assert event.published_at is None
    assert "EventNotRouted" in event.last_error


def test_broker_down_after_commit_doesnt_break_the_checkout(
    customer, monkeypatch, caplog, django_capture_on_commit_callbacks
):
    """Redis down: the task can't be queued, the order is still created; beat sends it later."""

    def broker_down():
        raise ConnectionError("Redis is down")

    monkeypatch.setattr(publish_pending_events, "delay", broker_down)

    with django_capture_on_commit_callbacks(execute=True):
        order = create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)

    assert order.pk
    assert OutboxEvent.objects.get().published_at is None
    assert "next beat run" in caplog.text


def test_task_sends_everything_in_batches(customer, analytics_queue, monkeypatch):
    """A backlog bigger than one batch goes out in several runs of the loop."""
    monkeypatch.setattr("outbox.publisher.BATCH_SIZE", 1)
    order = create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)
    cancel_order(order.pk)

    assert publish_pending_events() == 2
    assert len(analytics_queue()) == 2


# ---------------------------------------------------------------------------
# Cleanup, command, admin
# ---------------------------------------------------------------------------


def make_event(*, published_days_ago=None, created_days_ago=0):
    event = OutboxEvent.objects.create(type="order.created", order_id=1, payload={})
    now = timezone.now()
    OutboxEvent.objects.filter(pk=event.pk).update(
        created_at=now - timedelta(days=created_days_ago),
        published_at=(
            None if published_days_ago is None else now - timedelta(days=published_days_ago)
        ),
    )
    return event


def test_old_sent_events_are_deleted_unsent_ones_never(db):
    old_sent = make_event(published_days_ago=31, created_days_ago=31)
    recent_sent = make_event(published_days_ago=1)
    old_unsent = make_event(created_days_ago=90)

    assert delete_old_events() == 1

    remaining = set(OutboxEvent.objects.values_list("pk", flat=True))
    assert remaining == {recent_sent.pk, old_unsent.pk}
    assert old_sent.pk not in remaining


def test_publish_outbox_command(customer, analytics_queue, capsys):
    create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)

    call_command("publish_outbox")

    assert "Sent: 1, still waiting: 0" in capsys.readouterr().out
    assert len(analytics_queue()) == 1


def test_publish_outbox_command_without_rabbitmq(db, settings, capsys):
    settings.RABBITMQ_URL = ""

    call_command("publish_outbox")

    assert "not configured" in capsys.readouterr().err


def test_publish_outbox_command_reports_waiting_events(customer, settings, capsys):
    create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)
    settings.RABBITMQ_URL = "amqp://guest:guest@127.0.0.1:1//"

    call_command("publish_outbox")

    output = capsys.readouterr()
    assert "Sent: 0, still waiting: 1" in output.out
    assert "last_error" in output.err


@pytest.fixture
def superuser_client(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    return client


def test_admin_shows_the_events_read_only(customer, superuser_client):
    create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)
    event = OutboxEvent.objects.get()

    changelist = superuser_client.get(
        reverse("admin:outbox_outboxevent_changelist"), {"sent": "no"}
    )
    detail = superuser_client.get(reverse("admin:outbox_outboxevent_change", args=[event.pk]))

    assert changelist.status_code == 200
    assert str(event.event_id) in changelist.text
    # The "sent" column: a red cross for a waiting event
    assert "icon-no.svg" in changelist.text
    assert detail.status_code == 200
    # View only: no add page, no delete
    assert superuser_client.get(reverse("admin:outbox_outboxevent_add")).status_code == 403
    assert (
        superuser_client.get(
            reverse("admin:outbox_outboxevent_delete", args=[event.pk])
        ).status_code
        == 403
    )


def test_admin_filter_of_sent_events(db, superuser_client):
    sent = make_event(published_days_ago=1)
    url = reverse("admin:outbox_outboxevent_changelist")

    assert str(sent.event_id) in superuser_client.get(url, {"sent": "yes"}).text
    assert str(sent.event_id) not in superuser_client.get(url, {"sent": "no"}).text


def test_admin_action_sends_the_waiting_events(customer, superuser_client, analytics_queue):
    create_order(customer, {format_id(BookFactory()): 1}, **DELIVERY)
    event = OutboxEvent.objects.get()

    response = superuser_client.post(
        reverse("admin:outbox_outboxevent_changelist"),
        {"action": "publish_now", "_selected_action": [event.pk]},
        follow=True,
    )

    assert response.status_code == 200
    assert [message.level_tag for message in response.context["messages"]] == ["success"]
    assert len(analytics_queue()) == 1
