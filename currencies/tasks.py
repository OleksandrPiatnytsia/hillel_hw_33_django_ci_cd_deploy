"""Celery task: the daily NBU update of the exchange rates.

Put into the queue by Celery Beat (CELERY_BEAT_SCHEDULE in
config/settings/base.py) several times every afternoon: the NBU publishes
the rates of the next day at about 15:30 Kyiv time, and the first run after
that saves them. The other runs of the day save the same numbers again
(update_or_create), nothing breaks.
"""

from celery import shared_task

from .services import update_current_rates


# Retries: only for errors that may pass by themselves. requests'
# RequestException (no connection, timeout, HTTP 5xx of the NBU) is an
# OSError. NBUError (an answer of another shape) is not retried: it fails
# the same way every time, and it goes to the log and to Sentry.
@shared_task(
    autoretry_for=(OSError,),
    max_retries=3,
    retry_backoff=60,
    retry_backoff_max=10 * 60,
    retry_jitter=True,
)
def update_exchange_rates():
    # Today and the newest day (often tomorrow), see update_current_rates().
    # The return value is shown in Flower and the worker log.
    return [
        {
            "date": result.date.isoformat(),
            "saved": {code: str(value) for code, value in result.saved.items()},
            "kept_manual": result.kept_manual,
            "missing": result.missing,
        }
        for result in update_current_rates()
    ]
