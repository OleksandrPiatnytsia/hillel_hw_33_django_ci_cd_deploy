"""python manage.py publish_outbox: send the unsent events of the outbox now.

The same code as the beat task (outbox.tasks.publish_pending_events), by hand:
after RabbitMQ or Analytics was down, to see at once whether it works again.

    python manage.py publish_outbox
    Sent: 3, still waiting: 0
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from outbox.models import OutboxEvent
from outbox.tasks import publish_pending_events


class Command(BaseCommand):
    help = "Send the unsent events of the outbox to RabbitMQ (Analytics)."

    def handle(self, *args, **options):
        if not settings.RABBITMQ_URL:
            self.stderr.write("RabbitMQ is not configured (RABBITMQ_URL / RABBITMQ_HOST).")
            return
        sent = publish_pending_events()
        waiting = OutboxEvent.objects.filter(published_at__isnull=True).count()
        self.stdout.write(f"Sent: {sent}, still waiting: {waiting}")
        if waiting:
            # The reason is in the row (admin) and in the log line above
            self.stderr.write("Some events were not sent: see last_error in the admin.")
