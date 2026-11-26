from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AnalyticsConfig(AppConfig):
    """The sales page of the managers: the reports of the Analytics service.

    No models: the numbers live in Analytics, here they are only read
    (client.py), cached (reports.py) and shown (views.py).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "analytics"
    verbose_name = _("Sales analytics")
