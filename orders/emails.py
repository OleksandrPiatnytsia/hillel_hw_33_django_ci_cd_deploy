"""Emails about orders to the customer.

Every email has two parts in one message (multipart/alternative):
a plain text version and an HTML version; the mail client shows the HTML
one, a text-only client or a spam filter reads the text one.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import translation

from .models import Order

logger = logging.getLogger(__name__)  # "orders.emails"


def send_order_email(order, template_prefix, extra_context=None, raise_errors=False):
    """Render <prefix>_subject.txt / .txt / .html and send them to the customer.

    Used for every email about an order: "order created" here, "payment
    received" in payments/emails.py. extra_context: more template variables.

    raise_errors=False (default): never raises. An email is a notification,
    the order is already saved: a Gmail outage, a wrong App Password or a
    timeout must not turn a successful checkout into an error page, so
    every problem is only logged (with the traceback) for the developer.
    raise_errors=True: the Celery tasks (orders/tasks.py). The error is
    logged AND raised again, so the task can retry the email later.
    """
    # The email is written in the RECIPIENT's language (User.language), not in
    # the language of the current request: it may be sent by a manager in the
    # admin, by the Stripe webhook (no user at all) or by a command.
    # override(): this language only inside the "with" block, then the
    # previous one comes back (the manager's admin stays in their language).
    with translation.override(order.user.language):
        return _send(order, template_prefix, extra_context, raise_errors)


def _send(order, template_prefix, extra_context, raise_errors):
    context = {
        "order": order,
        "user": order.user,
        # Absolute link: the email is read outside the site
        "order_url": f"{settings.SITE_URL}{order.get_absolute_url()}",
        "site_url": settings.SITE_URL,
        **(extra_context or {}),
    }
    try:
        # The subject must be one line: a template file ends with "\n"
        subject = render_to_string(f"{template_prefix}_subject.txt", context).strip()
        message = EmailMultiAlternatives(
            subject=subject,
            body=render_to_string(f"{template_prefix}.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.user.email],
        )
        message.attach_alternative(
            render_to_string(f"{template_prefix}.html", context), "text/html"
        )
        message.send()  # the "default" mailer from settings.MAILERS
    except Exception:
        # Broad on purpose (SMTP errors, OSError for network problems,
        # template mistakes): see the docstring. logger.exception() adds
        # the traceback to the log.
        # order.pk, not order: str(order) is translated ("Замовлення #5"),
        # the log stays in English
        logger.exception(
            "Email %s for order #%s to %s failed", template_prefix, order.pk, order.user.email
        )
        if raise_errors:
            raise
        return False

    logger.info("Email %s for order #%s sent to %s", template_prefix, order.pk, order.user.email)
    return True


def send_order_cancelled_email(order_id, raise_errors=False):
    """ "Order #N is cancelled: it was not paid in time": the automatic
    cancellation of an unpaid order (cancel_unpaid_orders, Celery Beat).

    Takes the id: called after COMMIT, like send_order_created_email().
    """
    order = Order.objects.select_related("user").prefetch_related("items").get(pk=order_id)
    return send_order_email(order, "orders/emails/order_cancelled", raise_errors=raise_errors)


def send_order_created_email(order_id, raise_errors=False):
    """ "Order #N is created": items, total, delivery data, link to the order.

    Takes the id, not the object: it is called after COMMIT
    (transaction.on_commit) and reads the saved order from the database.
    """
    order = Order.objects.select_related("user").prefetch_related("items").get(pk=order_id)
    return send_order_email(order, "orders/emails/order_created", raise_errors=raise_errors)
