"""Sending the outbox to RabbitMQ: publish_pending().

    unsent rows (oldest first, locked: FOR UPDATE SKIP LOCKED)
      -> one connection, one message per row:
           exchange "bookstore.events" (topic), routing key = event type,
           persistent, message_id = event_id, JSON
      -> RabbitMQ confirms it (publisher confirms) -> published_at = now
      -> an error: failed_attempts + 1, last_error, stop; the next run tries again

Guarantees:
- nothing is lost: a row is marked sent only after RabbitMQ's confirm,
  "stored in a durable queue";
- at least once, not exactly once: if the process dies between the confirm
  and the UPDATE, the row is sent again. Analytics skips a repeated event_id;
- the order of one order's events stays: oldest first, and the run stops at
  the first failure instead of skipping the failed row.

mandatory=True: a message no queue is bound for (a fresh RabbitMQ, Analytics
never started, so there is no queue "analytics.events" yet) would be
confirmed and DROPPED. With mandatory RabbitMQ returns it first, and the row
stays unsent until the queue exists.
"""

import json
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from kombu import Connection, Exchange

from .models import OutboxEvent

logger = logging.getLogger(__name__)  # "outbox.publisher"

# Rows per run: a long backlog (RabbitMQ was down for a day) goes out in
# parts, each run holds its locks for a short time
BATCH_SIZE = 100
# Seconds to wait for RabbitMQ: a run must not hang on a dead server
CONNECT_TIMEOUT = 5


class EventNotRouted(Exception):
    """RabbitMQ returned the message: no queue is bound for its routing key."""


def events_exchange():
    # The same declaration as in Analytics (events/topology.py): whoever
    # starts first creates it, for the other one it is a no-op
    return Exchange(settings.EVENTS_EXCHANGE, type="topic", durable=True)


def connect():
    """A connection with publisher confirms: publish() returns only after RabbitMQ's "stored"."""
    return Connection(
        settings.RABBITMQ_URL,
        connect_timeout=CONNECT_TIMEOUT,
        transport_options={"confirm_publish": True},
    )


def publish_pending(limit=None):
    """Send up to `limit` (default BATCH_SIZE) unsent events. Returns how many were sent.

    No RabbitMQ configured (RABBITMQ_URL = "") -> sends nothing, the rows wait.
    """
    if not settings.RABBITMQ_URL:
        logger.debug("RABBITMQ_URL is not set: the outbox is not sent")
        return 0

    with transaction.atomic():
        # SKIP LOCKED: two workers (the task after a COMMIT and the beat run
        # at the same second) take different rows instead of sending the
        # same ones twice or waiting for each other
        events = list(
            OutboxEvent.objects.filter(published_at__isnull=True)
            .select_for_update(skip_locked=True)
            .order_by("created_at", "pk")[: limit or BATCH_SIZE]
        )
        if not events:
            return 0
        sent = _send(events)
    if sent:
        logger.info("Outbox: %s event(s) sent to RabbitMQ", sent)
    return sent


def _send(events):
    """Publish the rows one by one; mark each sent one. Returns the number sent."""
    sent = 0
    current = events[0]
    try:
        with connect() as connection:
            connection.ensure_connection(max_retries=1)
            returned = []
            producer = connection.Producer(
                exchange=events_exchange(),
                # Called by kombu while publish() waits for the confirm, if
                # RabbitMQ returns the message (mandatory, no queue)
                on_return=lambda exception, exchange, routing_key, message: returned.append(
                    routing_key
                ),
            )
            for current in events:
                producer.publish(
                    json.dumps(current.payload),
                    routing_key=current.type,
                    content_type="application/json",
                    content_encoding="utf-8",
                    message_id=str(current.event_id),
                    delivery_mode=2,  # persistent: survives a restart of RabbitMQ
                    mandatory=True,
                    declare=[events_exchange()],
                    # No kombu retries here: the beat run a minute later is the retry
                    retry=False,
                )
                if returned:
                    raise EventNotRouted(
                        f"no queue is bound to {settings.EVENTS_EXCHANGE} "
                        f"for {current.type!r} (is Analytics started?)"
                    )
                current.published_at = timezone.now()
                current.save(update_fields=["published_at"])
                sent += 1
    except Exception as error:
        # Everything after this row stays unsent too: sent later in order
        current.failed_attempts += 1
        current.last_error = f"{type(error).__name__}: {error}"[:2000]
        current.save(update_fields=["failed_attempts", "last_error"])
        logger.warning(
            "Outbox: event %s (%s, order #%s) not sent, try %s: %s",
            current.event_id,
            current.type,
            current.order_id,
            current.failed_attempts,
            current.last_error,
        )
    return sent
