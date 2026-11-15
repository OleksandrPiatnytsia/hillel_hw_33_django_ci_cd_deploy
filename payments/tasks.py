"""Celery tasks of payments."""

from celery import shared_task

from orders.tasks import EMAIL_RETRY

from .emails import send_payment_received_email


@shared_task(**EMAIL_RETRY)
def send_payment_received_email_task(payment_id):
    """ "We received 14,31 $" in the background (payments.services)."""
    send_payment_received_email(payment_id, raise_errors=True)
