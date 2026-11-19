"""The outbox: events of the orders waiting to be sent to RabbitMQ.

Why a table and not a message right away ("transactional outbox"):

    with transaction.atomic():
        order.status = "cancelled"; order.save()
        OutboxEvent.objects.create(...)       <- the same COMMIT

The event exists exactly when the change of the order exists: a rolled back
order leaves no event, and a saved order always has its event, even if
RabbitMQ, Redis or the worker is down at that moment. A message sent right
from the view could be lost (RabbitMQ down) or announce an order that is then
rolled back. outbox.publisher sends the rows later and marks them sent only
after RabbitMQ has confirmed them.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class OutboxEvent(models.Model):
    class Type(models.TextChoices):
        # The value is the routing key in RabbitMQ and the "type" of the
        # message (the contract of Analytics, docs/events.md)
        ORDER_CREATED = "order.created", _("Order created")
        ORDER_PAID = "order.paid", _("Order paid")
        ORDER_CANCELLED = "order.cancelled", _("Order cancelled")

    # The id of the message for Analytics: a repeated id is skipped there,
    # so sending the same row twice (a crash between "sent" and "marked")
    # changes nothing
    event_id = models.UUIDField(_("event id"), default=uuid.uuid4, unique=True, editable=False)
    type = models.CharField(_("type"), max_length=30, choices=Type.choices)
    # The order this event is about. A plain number, not a foreign key: the
    # row is a record of what was sent, it doesn't depend on the order row
    # (and the admin filters by it without a JOIN)
    order_id = models.PositiveIntegerField(_("order"), db_index=True)
    # The whole body of the message, built when the event happened: the
    # order as it was THEN, even if it is sent an hour later
    payload = models.JSONField(_("payload"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    # Empty = not sent yet. Set only after RabbitMQ confirmed the message
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    # FAILED tries only, and the last error: for the admin and the logs.
    # A sent event usually has 0 (it went out on the first try); 2 = it
    # went out on the third try, or still waits after two failures
    failed_attempts = models.PositiveIntegerField(_("failed attempts"), default=0)
    last_error = models.TextField(_("last error"), blank=True)

    class Meta:
        # Sent in the order they happened: created -> paid of one order
        ordering = ["created_at", "pk"]
        verbose_name = _("outbox event")
        verbose_name_plural = _("outbox events")
        indexes = [
            # The publisher looks only for unsent rows. A partial index
            # holds only them: small and fast, while the sent rows (almost
            # all of the table) are not in it at all
            models.Index(
                fields=["created_at"],
                condition=models.Q(published_at__isnull=True),
                name="outbox_unpublished_idx",
            ),
        ]

    def __str__(self):
        return f"{self.type} #{self.order_id} ({self.event_id})"
