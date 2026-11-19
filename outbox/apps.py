from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OutboxConfig(AppConfig):
    name = "outbox"
    # Section title in the admin
    verbose_name = _("Events for Analytics")
