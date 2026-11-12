"""Celery tasks of orders: the email, the hourly cleanup, the daily report.

Run by the worker (service "celery"); the periodic ones are put into the
queue by Celery Beat (CELERY_BEAT_SCHEDULE in config/settings/base.py).
"""

from datetime import date, timedelta

from celery import shared_task
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from .emails import send_order_cancelled_email, send_order_created_email
from .reports import build_daily_report, send_daily_report_email

# Retries of a failed email: only for errors that may pass by themselves.
# OSError covers the network (ConnectionRefusedError, timeouts) and every
# smtplib.SMTPException (a subclass of OSError): Gmail down, "try later".
# A template mistake or a missing order is not retried: it fails the same
# way every time.
# retry_backoff=60: wait 60 s, then 120 s, then 240 s (doubles every time);
# retry_jitter: a random part of it, so 100 failed emails don't all come
# back in the same second.
EMAIL_RETRY = {
    "autoretry_for": (OSError,),
    "max_retries": 3,
    "retry_backoff": 60,
    "retry_backoff_max": 10 * 60,
    "retry_jitter": True,
}


@shared_task(**EMAIL_RETRY)
def send_order_created_email_task(order_id):
    """ "Order #N is created" in the background (orders.services.create_order)."""
    send_order_created_email(order_id, raise_errors=True)


@shared_task(**EMAIL_RETRY)
def send_order_cancelled_email_task(order_id):
    """ "Order #N is cancelled" after the automatic cancellation
    (orders.services.cancel_order(..., notify_customer=True))."""
    send_order_cancelled_email(order_id, raise_errors=True)


@shared_task
def cancel_unpaid_orders():
    """Every hour: the cancel_unpaid_orders command with the age from settings.

    The same code as by hand (python manage.py cancel_unpaid_orders): the
    command logs every cancelled order and queues the "order cancelled"
    email for its customer.
    """
    call_command("cancel_unpaid_orders", f"--older-than={settings.ORDER_UNPAID_MAX_AGE_HOURS}h")


@shared_task(**EMAIL_RETRY)
def send_daily_report(day=None):
    """Every morning: the report of yesterday to the "Managers" group.

    day: "2026-11-10" to send the report of another day by hand:
        from orders.tasks import send_daily_report
        send_daily_report.delay("2026-11-10")
    (a string, not a date: task arguments go through the broker as JSON)
    """
    if day is None:
        report_day = timezone.localdate() - timedelta(days=1)
    else:
        report_day = date.fromisoformat(day)
    return send_daily_report_email(build_daily_report(report_day))
