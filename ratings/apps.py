from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RatingsConfig(AppConfig):
    name = "ratings"
    # Section title in the admin
    verbose_name = _("Ratings")
