from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CurrenciesConfig(AppConfig):
    name = "currencies"
    # Section title in the admin
    verbose_name = _("Currencies")

    def ready(self):
        # Connects the receivers: a saved / deleted rate or currency clears
        # the cached current rates (currencies/signals.py)
        from . import signals  # noqa: F401
