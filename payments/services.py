"""Changes of payments and the order's payment status.

Every function here:
- runs in transaction.atomic();
- locks the ORDER first (select_for_update), then works with its payments.
  The same lock as in orders.services.cancel_order(): a payment and a
  cancellation of one order never run at the same time, and two payments
  of one order can't both read the old sum (refresh_payment_status());
- ends with order.refresh_payment_status() — the only place that changes
  Order.payment_status.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from config.celery import enqueue_on_commit
from orders.models import Order

from .models import Payment
from .providers.base import PaymentProviderError
from .providers.registry import ONLINE_PROVIDER, get_provider
from .tasks import send_payment_received_email_task

logger = logging.getLogger(__name__)  # "payments.services"


class PaymentError(Exception):
    """A payment can't be recorded; the text can be shown to the user."""


def _lock_order(order_id):
    return Order.objects.select_for_update().get(pk=order_id)


def record_manual_payment(order_id, amount, *, note="", recorded_by=None):
    """A manager received money outside the site: save it as a succeeded payment.

    amount may be any part of what is still due (partially_paid), but not
    more: 2500 typed instead of 250 is caught here, not found later.
    Returns the new Payment.
    """
    amount = Decimal(amount)
    if amount <= 0:
        raise PaymentError(_("The amount must be greater than 0."))

    with transaction.atomic():
        order = _lock_order(order_id)
        if order.status == Order.Status.CANCELLED:
            raise PaymentError(
                _("%(order)s is cancelled, payments can't be added.") % {"order": order}
            )
        due = order.amount_due
        if amount > due:
            raise PaymentError(
                _("%(order)s: only %(due)s UAH is due, %(amount)s UAH is too much.")
                % {"order": order, "due": due, "amount": amount}
            )

        payment = Payment.objects.create(
            order=order,
            provider=Payment.Provider.MANUAL,
            amount=amount,
            status=Payment.Status.SUCCEEDED,
            paid_at=timezone.now(),
            details={
                "note": note,
                # Who entered it: the admin form passes request.user
                "recorded_by": recorded_by.get_username() if recorded_by else None,
            },
        )
        order.refresh_payment_status()
        if order.payment_status == Order.PaymentStatus.PAID:
            # One email when the order is fully paid, not one per part
            enqueue_on_commit(send_payment_received_email_task, payment.pk)

    logger.info(
        "Manual payment %s UAH for order #%s recorded (%s)", amount, order.pk, order.payment_status
    )
    return payment


def mark_payment_succeeded(payment_id, *, details=None):
    """The provider confirmed the money (Stripe webhook, stage 7).

    Idempotent: providers deliver the same notification more than once
    (retries after a timeout); a second call for an already succeeded
    payment changes nothing and returns it as is.
    Returns the Payment.
    """
    with transaction.atomic():
        # The order id without locking the payment first: lock order -> payment,
        # always in this order (the same as everywhere else), no deadlocks
        order_id = Payment.objects.values_list("order_id", flat=True).get(pk=payment_id)
        order = _lock_order(order_id)
        payment = Payment.objects.select_for_update().get(pk=payment_id)

        if payment.status == Payment.Status.SUCCEEDED:
            logger.info("Payment %s is already succeeded, nothing to do", payment.pk)
            return payment
        if payment.status != Payment.Status.PENDING:
            # expired / failed and then "paid": the provider says the money
            # is received, so it is recorded, but somebody should look at it
            logger.warning("Payment %s was %s and is now succeeded", payment.pk, payment.status)

        payment.status = Payment.Status.SUCCEEDED
        payment.paid_at = timezone.now()
        if details:
            payment.details = {**payment.details, **details}
        payment.save(update_fields=["status", "paid_at", "details", "updated_at"])
        order.refresh_payment_status()
        # After COMMIT, like "order created". Only here, after the
        # "already succeeded" check above: the webhook and the return page
        # both confirm the same payment, the customer gets one email.
        # A Celery task, retried on failure (payments/tasks.py).
        enqueue_on_commit(send_payment_received_email_task, payment.pk)

        if order.status == Order.Status.CANCELLED:
            # Paid after the order was cancelled (e.g. cancel_unpaid_orders
            # ran while the customer was on the Stripe page): the money must
            # be returned by a manager
            logger.warning("Order #%s is cancelled but received payment %s", order.pk, payment.pk)

    logger.info(
        "Payment %s for order #%s succeeded (%s)", payment.pk, order.pk, order.payment_status
    )
    return payment


def mark_payment_unsuccessful(payment_id, status, *, details=None):
    """The payment didn't happen: status = failed or expired.

    Only a pending payment changes: a late "expired" must not undo a
    "succeeded" that came first. The order is NOT cancelled: the customer
    can press "Pay" again, which creates a new Payment.
    Returns the Payment.
    """
    if status not in (Payment.Status.FAILED, Payment.Status.EXPIRED):
        raise ValueError(f"status must be failed or expired, not {status!r}")

    with transaction.atomic():
        order_id = Payment.objects.values_list("order_id", flat=True).get(pk=payment_id)
        order = _lock_order(order_id)
        payment = Payment.objects.select_for_update().get(pk=payment_id)

        if payment.status != Payment.Status.PENDING:
            logger.info("Payment %s is %s, %s ignored", payment.pk, payment.status, status)
            return payment

        payment.status = status
        if details:
            payment.details = {**payment.details, **details}
        payment.save(update_fields=["status", "details", "updated_at"])
        # A pending payment never counted, so the sum doesn't change; kept
        # for the rule "every payment change ends with a refresh"
        order.refresh_payment_status()

    logger.info("Payment %s for order #%s is %s", payment.pk, order.pk, status)
    return payment


# ---------------------------------------------------------------------------
# Online payment (Stripe Checkout)
# ---------------------------------------------------------------------------

# A payment page that expires sooner than this is not offered again:
# the customer needs time to type the card details
MIN_TIME_LEFT_ON_PAGE = timedelta(minutes=5)


def start_online_payment(order_id, user, request):
    """The "Pay" button: return the URL of the provider's payment page.

    1. In a transaction, with the order locked:
       - checks: own order, not cancelled, something left to pay;
       - an open page of an earlier attempt for the same amount -> reuse it
         (two clicks on "Pay", or "back" from Stripe and "Pay" again,
         must not create two pages that could both be paid);
       - otherwise a new Payment(pending) for the amount still due.
    2. AFTER the transaction: the request to the provider. A network call
       inside the transaction would keep the order locked for seconds
       (everyone else waits), and a rollback can't undo it anyway.
       If the provider fails, the Payment becomes "failed" (kept for history).
    Raises PaymentError with a text for the customer.
    """
    provider = get_provider(ONLINE_PROVIDER)
    outdated = []  # open pages of earlier attempts that can't be reused

    with transaction.atomic():
        order = _lock_order(order_id)
        if order.user_id != user.pk:
            raise PaymentError(_("Order not found."))
        if order.status == Order.Status.CANCELLED:
            raise PaymentError(_("%(order)s is cancelled.") % {"order": order})
        due = order.amount_due
        if due <= 0:
            raise PaymentError(_("%(order)s is already paid.") % {"order": order})

        now = timezone.now()
        for payment in order.payments.filter(provider=provider.name, status=Payment.Status.PENDING):
            url = payment.details.get("url")
            expires_at = payment.details.get("expires_at", 0)
            if not url:
                # Created a moment ago by another click, the request to the
                # provider is still running: no second page
                if payment.created_at > now - timedelta(minutes=1):
                    raise PaymentError(
                        _("The payment is being prepared, please try again in a minute.")
                    )
                continue
            if payment.amount == due and expires_at > (now + MIN_TIME_LEFT_ON_PAGE).timestamp():
                logger.info("Payment %s: reusing the open payment page", payment.pk)
                return url
            outdated.append(payment)

        payment = Payment.objects.create(
            order=order,
            provider=provider.name,
            amount=due,
            status=Payment.Status.PENDING,
        )

    for old in outdated:
        close_payment_page(old)

    try:
        session = provider.start(payment, request)
    except PaymentProviderError as error:
        mark_payment_unsuccessful(payment.pk, Payment.Status.FAILED, details={"error": str(error)})
        raise PaymentError(str(error)) from error

    payment.external_id = session.external_id
    payment.details = {**payment.details, "url": session.url, "expires_at": session.expires_at}
    payment.save(update_fields=["external_id", "details", "updated_at"])
    logger.info(
        "Payment %s for order #%s: payment page created (%s)",
        payment.pk,
        order.pk,
        session.external_id,
    )
    return session.url


def sync_payment(payment):
    """Ask the provider about a pending payment and save the answer.

    Used when the customer comes back from the payment page: it shows the
    result at once, without waiting for the webhook (stage 7), and works
    even if the webhook is not set up. Both paths end in the same
    idempotent functions, so whichever comes first wins and the second
    changes nothing.
    Returns the fresh Payment.
    """
    if payment.status != Payment.Status.PENDING or not payment.external_id:
        return payment
    try:
        status = get_provider(payment.provider).fetch_status(payment)
    except PaymentProviderError:
        return payment  # can't tell now: stays pending, the webhook decides
    if status == Payment.Status.SUCCEEDED:
        return mark_payment_succeeded(payment.pk)
    if status in (Payment.Status.EXPIRED, Payment.Status.FAILED):
        return mark_payment_unsuccessful(payment.pk, status)
    return payment


def close_payment_page(payment):
    """Expire the provider's page of a pending payment; it becomes "expired".

    If the provider says it's too late (already paid), the payment stays
    pending: the money is real, sync_payment() / the webhook records it.
    Best effort: a provider error is logged, nothing is raised.
    """
    try:
        closed = get_provider(payment.provider).cancel(payment)
    except PaymentProviderError:
        logger.warning("Payment %s: can't close the payment page", payment.pk)
        return
    if closed:
        mark_payment_unsuccessful(payment.pk, Payment.Status.EXPIRED, details={"closed_by": "site"})
    else:
        sync_payment(payment)


def close_open_payments(order_id):
    """After an order is cancelled: no open payment page may stay payable.

    Called by orders.services.cancel_order() with transaction.on_commit().
    """
    pending = Payment.objects.filter(order_id=order_id, status=Payment.Status.PENDING)
    # Without external_id the provider has no page yet: nothing to close
    for payment in pending.exclude(external_id=""):
        close_payment_page(payment)
