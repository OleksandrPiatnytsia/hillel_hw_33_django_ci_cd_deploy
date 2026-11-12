"""Integration: paying for an order with Stripe Checkout (the fake client).

The customer's side:  "Pay" -> Stripe page -> back to /payments/success/
Stripe's side:        POST /payments/webhook/stripe/ with a signed event
Both paths must give the same result and only one email.
"""

from decimal import Decimal

import pytest
import stripe
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from orders.models import Order
from payments.models import Payment

from ..factories import BookFactory, OrderFactory
from ..fakes import stripe_event_payload, stripe_webhook_headers
from ..helpers import message_levels

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(customer):
    """A new unpaid order of the customer for 250 UAH."""
    return OrderFactory(user=customer, items=[(BookFactory(price=Decimal("250.00")), 1)])


def press_pay(client, order):
    return client.post(reverse("payments:pay", args=[order.pk]))


def send_webhook(client, event_type, session_id, **session_fields):
    payload = stripe_event_payload(event_type, session_id, **session_fields)
    return client.post(
        reverse("payments:webhook", args=["stripe"]),
        data=payload,
        content_type="application/json",
        headers=stripe_webhook_headers(payload),
    )


def test_pay_on_stripe_and_come_back_to_success_page(
    order, customer_client, fake_stripe, mailoutbox, django_capture_on_commit_callbacks
):
    # 1. "Pay" -> redirect to the Stripe page
    response = press_pay(customer_client, order)

    payment = order.payments.get()
    session = fake_stripe.sessions[payment.external_id]
    assertRedirects(response, session.url, fetch_redirect_response=False)
    params = fake_stripe.created[0]["params"]
    assert params["line_items"][0]["price_data"]["unit_amount"] == 25000
    assert params["metadata"] == {"order_id": str(order.pk), "payment_id": str(payment.pk)}
    assert (
        params["success_url"]
        == "http://testserver/payments/success/?session_id={CHECKOUT_SESSION_ID}"
    )

    # 2. The customer pays; Stripe sends them back with the session id
    fake_stripe.pay(session.id)
    with django_capture_on_commit_callbacks(execute=True):
        response = customer_client.get(reverse("payments:success"), {"session_id": session.id})

    # 3. The site asked Stripe itself and recorded the money
    assert response.status_code == 200
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == Payment.Status.SUCCEEDED
    assert payment.paid_at is not None
    assert order.payment_status == Order.PaymentStatus.PAID
    assert len(mailoutbox) == 1
    assert f"#{order.pk}" in mailoutbox[0].subject


def test_second_click_on_pay_reuses_the_open_stripe_page(order, customer_client, fake_stripe):
    first = press_pay(customer_client, order)
    second = press_pay(customer_client, order)

    assert first.url == second.url
    assert len(fake_stripe.created) == 1
    assert order.payments.count() == 1


def test_webhook_and_return_page_both_confirm_but_one_email(
    order, client, customer_client, fake_stripe, mailoutbox, django_capture_on_commit_callbacks
):
    press_pay(customer_client, order)
    session_id = order.payments.get().external_id
    fake_stripe.pay(session_id)

    with django_capture_on_commit_callbacks(execute=True):
        first = send_webhook(client, "checkout.session.completed", session_id)
        # Stripe retries the same event (e.g. our answer was too slow)
        again = send_webhook(client, "checkout.session.completed", session_id)
        # ... and the customer comes back to the success page
        customer_client.get(reverse("payments:success"), {"session_id": session_id})

    assert (first.status_code, again.status_code) == (200, 200)
    order.refresh_from_db()
    assert order.payment_status == Order.PaymentStatus.PAID
    assert len(mailoutbox) == 1


def test_expired_stripe_page_then_pay_again_with_a_new_page(
    order, client, customer_client, fake_stripe
):
    press_pay(customer_client, order)
    old = order.payments.get()
    fake_stripe.expire_session(old.external_id)

    response = send_webhook(
        client,
        "checkout.session.expired",
        old.external_id,
        payment_status="unpaid",
        status="expired",
    )

    assert response.status_code == 200
    old.refresh_from_db()
    order.refresh_from_db()
    assert old.status == Payment.Status.EXPIRED
    assert order.payment_status == Order.PaymentStatus.UNPAID

    press_pay(customer_client, order)

    assert len(fake_stripe.created) == 2
    assert order.payments.filter(status=Payment.Status.PENDING).count() == 1


def test_webhook_for_unknown_session_is_accepted_and_ignored(client):
    response = send_webhook(client, "checkout.session.completed", "cs_test_not_ours")

    assert response.status_code == 200  # 2xx, or Stripe would retry for days
    assert not Payment.objects.exists()


def test_stripe_is_down_payment_fails_and_order_page_shows_error(
    order, customer_client, fake_stripe
):
    fake_stripe.fail_with = stripe.APIConnectionError("Network is unreachable (test)")

    response = press_pay(customer_client, order)

    assertRedirects(response, order.get_absolute_url())
    assert message_levels(response) == ["error"]
    payment = order.payments.get()
    assert payment.status == Payment.Status.FAILED
    assert "error" in payment.details


def test_back_from_stripe_without_paying_keeps_order_unpaid(order, customer_client, fake_stripe):
    press_pay(customer_client, order)
    payment = order.payments.get()

    response = customer_client.get(reverse("payments:cancelled", args=[payment.pk]))

    assertRedirects(response, order.get_absolute_url())
    assert message_levels(response) == ["info"]
    order.refresh_from_db()
    assert order.payment_status == Order.PaymentStatus.UNPAID


def test_paid_order_cannot_be_cancelled_by_customer(order, client, customer_client, fake_stripe):
    press_pay(customer_client, order)
    session_id = order.payments.get().external_id
    fake_stripe.pay(session_id)
    send_webhook(client, "checkout.session.completed", session_id)

    response = customer_client.post(reverse("orders:cancel", args=[order.pk]))

    assert message_levels(response) == ["error"]
    order.refresh_from_db()
    assert order.status == Order.Status.NEW
    assert order.payment_status == Order.PaymentStatus.PAID
