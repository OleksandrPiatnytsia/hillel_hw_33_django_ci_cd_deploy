"""Unit tests of payments.services and the Stripe provider: the refusals and
the error paths (the happy paths are in tests/integration/test_payment_flow.py).

Stripe is the fake client (fixture fake_stripe), emails go to mailoutbox.
"""

import logging
from datetime import timedelta
from decimal import Decimal

import pytest
import stripe
from django.urls import reverse
from django.utils import timezone

from orders.models import Order
from payments.models import Payment
from payments.providers.base import PaymentProviderError
from payments.providers.stripe_checkout import StripeProvider
from payments.services import (
    PaymentError,
    close_payment_page,
    mark_payment_succeeded,
    mark_payment_unsuccessful,
    record_manual_payment,
    start_online_payment,
    sync_payment,
)

from ..factories import BookFactory, OrderFactory, PaymentFactory
from ..fakes import stripe_event_payload, stripe_webhook_headers

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(customer):
    """A new unpaid order of the customer for 250 UAH."""
    return OrderFactory(user=customer, items=[(BookFactory(price=Decimal("250.00")), 1)])


@pytest.fixture
def request_of(rf):
    """A GET request object for provider.start() (it builds the return URLs).
    rf: pytest-django's RequestFactory fixture."""
    return rf.get("/")


# ---------------------------------------------------------------------------
# record_manual_payment: what a manager may not enter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("amount", ["0", "-10"])
def test_manual_payment_must_be_positive(order, amount):
    with pytest.raises(PaymentError):
        record_manual_payment(order.pk, amount)

    assert not order.payments.exists()


def test_manual_payment_for_cancelled_order_is_refused(order):
    order.status = Order.Status.CANCELLED
    order.save()

    with pytest.raises(PaymentError):
        record_manual_payment(order.pk, "100")


# ---------------------------------------------------------------------------
# start_online_payment: when no Stripe page is created
# ---------------------------------------------------------------------------


def test_online_payment_of_someone_elses_order_is_refused(
    order, other_customer, request_of, fake_stripe
):
    with pytest.raises(PaymentError):
        start_online_payment(order.pk, other_customer, request_of)

    assert fake_stripe.created == []


def test_online_payment_of_cancelled_or_paid_order_is_refused(
    order, customer, request_of, fake_stripe
):
    record_manual_payment(order.pk, "250")  # fully paid

    with pytest.raises(PaymentError):
        start_online_payment(order.pk, customer, request_of)

    order.status = Order.Status.CANCELLED
    order.save()
    with pytest.raises(PaymentError):
        start_online_payment(order.pk, customer, request_of)

    assert fake_stripe.created == []


def test_double_click_while_the_page_is_being_prepared(order, customer, request_of, fake_stripe):
    # The first click created a pending payment, its Stripe request is still running (no url yet)
    PaymentFactory(order=order, external_id="", details={})

    with pytest.raises(PaymentError):
        start_online_payment(order.pk, customer, request_of)

    assert fake_stripe.created == []


def test_old_unfinished_attempt_does_not_block_a_new_page(order, customer, request_of, fake_stripe):
    stuck = PaymentFactory(order=order, external_id="", details={})
    Payment.objects.filter(pk=stuck.pk).update(created_at=timezone.now() - timedelta(minutes=5))

    url = start_online_payment(order.pk, customer, request_of)

    assert url.startswith("https://")
    assert len(fake_stripe.created) == 1


def test_stripe_not_configured_fails_the_payment(order, customer, request_of, settings):
    settings.STRIPE_SECRET_KEY = ""  # no fake client: the real provider checks the key first

    with pytest.raises(PaymentError):
        start_online_payment(order.pk, customer, request_of)

    assert order.payments.get().status == Payment.Status.FAILED


# ---------------------------------------------------------------------------
# Status changes
# ---------------------------------------------------------------------------


def test_unsuccessful_status_must_be_failed_or_expired(order):
    payment = PaymentFactory(order=order)

    with pytest.raises(ValueError):
        mark_payment_unsuccessful(payment.pk, Payment.Status.SUCCEEDED)


def test_late_expired_does_not_undo_a_succeeded_payment(order):
    payment = PaymentFactory(order=order)
    mark_payment_succeeded(payment.pk)

    mark_payment_unsuccessful(payment.pk, Payment.Status.EXPIRED)

    payment.refresh_from_db()
    assert payment.status == Payment.Status.SUCCEEDED


def test_money_for_an_expired_page_is_still_recorded_with_a_warning(order, caplog):
    payment = PaymentFactory(order=order, status=Payment.Status.EXPIRED)

    with caplog.at_level(logging.WARNING, logger="payments.services"):
        mark_payment_succeeded(payment.pk)

    order.refresh_from_db()
    assert order.payment_status == Order.PaymentStatus.PAID
    assert "was expired and is now succeeded" in caplog.text


def test_payment_after_cancellation_is_logged_for_a_manager(order, caplog):
    payment = PaymentFactory(order=order)
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)

    with caplog.at_level(logging.WARNING, logger="payments.services"):
        mark_payment_succeeded(payment.pk)

    assert "is cancelled but received payment" in caplog.text


# ---------------------------------------------------------------------------
# sync_payment / close_payment_page when Stripe doesn't answer
# ---------------------------------------------------------------------------


def test_sync_payment_when_stripe_is_down_keeps_pending(order, customer, request_of, fake_stripe):
    start_online_payment(order.pk, customer, request_of)
    payment = order.payments.get()
    fake_stripe.fail_with = stripe.APIConnectionError("down (test)")

    assert sync_payment(payment).status == Payment.Status.PENDING


def test_sync_payment_sees_an_expired_page(order, customer, request_of, fake_stripe):
    start_online_payment(order.pk, customer, request_of)
    payment = order.payments.get()
    fake_stripe.expire_session(payment.external_id)

    assert sync_payment(payment).status == Payment.Status.EXPIRED


def test_close_payment_page_when_stripe_is_down_changes_nothing(
    order, customer, request_of, fake_stripe, caplog
):
    start_online_payment(order.pk, customer, request_of)
    payment = order.payments.get()
    fake_stripe.fail_with = stripe.APIConnectionError("down (test)")

    close_payment_page(payment)

    payment.refresh_from_db()
    assert payment.status == Payment.Status.PENDING
    assert "can't close the payment page" in caplog.text


def test_close_payment_page_already_paid_records_the_money(
    order, customer, request_of, fake_stripe
):
    """Too late to close: the customer paid a second earlier. The money is real."""
    start_online_payment(order.pk, customer, request_of)
    payment = order.payments.get()
    fake_stripe.pay(payment.external_id)

    close_payment_page(payment)

    payment.refresh_from_db()
    assert payment.status == Payment.Status.SUCCEEDED


# ---------------------------------------------------------------------------
# Stripe webhook: the answers
# ---------------------------------------------------------------------------


def post_webhook(client, event_type, session_id, **session_fields):
    payload = stripe_event_payload(event_type, session_id, **session_fields)
    return client.post(
        reverse("payments:webhook", args=["stripe"]),
        data=payload,
        content_type="application/json",
        headers=stripe_webhook_headers(payload),
    )


def test_webhook_without_secret_in_settings_is_400(client, settings):
    settings.STRIPE_WEBHOOK_SECRET = ""

    assert post_webhook(client, "checkout.session.completed", "cs_test_1").status_code == 400


def test_webhook_of_other_event_types_is_accepted_and_ignored(client, order):
    payment = PaymentFactory(order=order, external_id="cs_test_1")

    response = post_webhook(client, "payment_intent.created", "cs_test_1")

    assert response.status_code == 200
    payment.refresh_from_db()
    assert payment.status == Payment.Status.PENDING


def test_webhook_delayed_payment_failed_marks_the_payment_failed(client, order):
    payment = PaymentFactory(order=order, external_id="cs_test_1")

    post_webhook(
        client, "checkout.session.async_payment_failed", "cs_test_1", payment_status="unpaid"
    )

    payment.refresh_from_db()
    assert payment.status == Payment.Status.FAILED


def test_webhook_completed_but_unpaid_waits_for_the_bank(client, order):
    """A bank debit: the page is completed, the money comes days later."""
    payment = PaymentFactory(order=order, external_id="cs_test_1")

    post_webhook(client, "checkout.session.completed", "cs_test_1", payment_status="unpaid")

    payment.refresh_from_db()
    assert payment.status == Payment.Status.PENDING


def test_stripe_provider_error_has_a_text_for_the_customer(fake_stripe):
    fake_stripe.fail_with = stripe.APIConnectionError("down (test)")
    payment = PaymentFactory(external_id="cs_test_1")

    with pytest.raises(PaymentProviderError) as error:
        StripeProvider().fetch_status(payment)

    assert str(error.value)  # shown to the customer, never Stripe's own text
    assert "down (test)" not in str(error.value)
