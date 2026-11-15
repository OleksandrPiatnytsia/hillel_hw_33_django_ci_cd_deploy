"""A changed rate or currency clears the cached current rates.

Without this a rate entered in the admin would show on the site only on
the next day (the cache key has the date in it, services.CACHE_KEY).

on_commit: the cache is cleared after the COMMIT. Cleared before it, a
request in between could read the old rates from the database and put
them back into the cache for the whole day.
"""

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Currency, ExchangeRate
from .services import clear_rates_cache


@receiver(post_save, sender=ExchangeRate)
@receiver(post_delete, sender=ExchangeRate)
@receiver(post_save, sender=Currency)
@receiver(post_delete, sender=Currency)
def rates_changed(sender, **kwargs):
    transaction.on_commit(clear_rates_cache)
