"""Emails about payments: "payment received"."""

from orders.emails import send_order_email

from .models import Payment


def send_payment_received_email(payment_id, raise_errors=False):
    """ "We received 14,31 $ for order #M": paid so far, still due, the status.

    Called after COMMIT (transaction.on_commit in payments.services):
    - Stripe: for every succeeded payment;
    - manual: only when the order becomes fully paid (a manager may enter
      several parts, one email per part would be noise).
    Never raises (send_order_email logs the problems), except with
    raise_errors=True: the Celery task, which retries (payments/tasks.py).
    """
    payment = Payment.objects.select_related("order__user").get(pk=payment_id)
    return send_order_email(
        payment.order,
        "payments/emails/payment_received",
        {"payment": payment},
        raise_errors=raise_errors,
    )
