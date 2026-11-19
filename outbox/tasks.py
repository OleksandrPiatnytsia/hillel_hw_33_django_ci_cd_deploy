"""Celery tasks of the outbox.

publish_pending_events: queued after the COMMIT of every event
(outbox.services) and by beat every minute (the safety net when RabbitMQ,
Redis or the worker was down). Both run the same publish_pending(): several
runs at the same time take different rows (SKIP LOCKED).

delete_old_events: beat at night, sent rows older than OUTBOX_KEEP_DAYS.
"""

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import OutboxEvent
from .publisher import publish_pending


@shared_task
def publish_pending_events():
    """Send every unsent event, in parts of BATCH_SIZE, until none is left or one fails."""
    total = 0
    while True:
        sent = publish_pending()
        total += sent
        # 0 = nothing left, or a failure (logged in publish_pending): stop,
        # the next beat run tries again
        if sent == 0:
            return total


@shared_task
def delete_old_events():
    """Unsent rows are never deleted: they still have to reach Analytics."""
    border = timezone.now() - timedelta(days=settings.OUTBOX_KEEP_DAYS)
    deleted, _ = OutboxEvent.objects.filter(published_at__lt=border).delete()
    return deleted
