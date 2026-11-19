"""Writing the events of the orders: record_event(), called inside the order's transaction.

    with transaction.atomic():
        ... change the order ...
        record_event(order, OutboxEvent.Type.ORDER_PAID)

Callers: orders.services.create_order() (order.created),
Order.refresh_payment_status() (order.paid), orders.services.cancel_order()
(order.cancelled). These are the only places where an order is created, its
payment status changes, or it is cancelled: the site, the API, the admin and
the commands all go through them.
"""

import logging
import uuid

from django.db import transaction
from django.utils import timezone

from .models import OutboxEvent
from .snapshot import event_body

logger = logging.getLogger(__name__)  # "outbox.services"


def record_event(order, event_type):
    """Add the event to the outbox; it is sent right after the COMMIT.

    Call it inside the transaction that changes the order: the row is saved
    and rolled back together with the order. (Outside a transaction it works
    too: the row is saved at once and on_commit() runs at once.)
    """
    event_id = uuid.uuid4()
    event = OutboxEvent.objects.create(
        event_id=event_id,
        type=event_type,
        order_id=order.pk,
        payload=event_body(event_id, event_type, timezone.now(), order),
    )
    # Dropped by Django if the transaction is rolled back: no task for an
    # event that doesn't exist
    transaction.on_commit(_publish_soon)
    return event


def _publish_soon():
    """Queue the publisher after the COMMIT; if Redis is down, leave it to beat.

    Not enqueue_on_commit() of the emails, which runs the task right here when
    the broker is down: the customer would wait for RabbitMQ (or its timeout)
    on the checkout page. The event is safe in the table, and the beat task
    publish_pending_events sends it within a minute.
    """
    # Imported here: tasks imports the publisher (kombu), not needed to
    # only write the row
    from .tasks import publish_pending_events

    try:
        publish_pending_events.delay()
    except Exception:
        logger.warning(
            "Celery broker unavailable: the outbox will be sent by the next beat run",
            exc_info=True,
        )
