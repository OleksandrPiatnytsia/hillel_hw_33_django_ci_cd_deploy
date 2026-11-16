"""Stage 5 of the currencies: payments in the currency of the order.

Stripe is asked for the order currency ("usd" for a USD order), the payment
keeps it, and the money is counted only if Stripe took exactly that sum in
exactly that currency. Manual payments, emails and pages show the sums with
the currency of the order.

The rate of every test: 1 USD = 45.4274 UAH.
"""

import logging
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from currencies.models import Currency, ExchangeRate
from orders.models import Order
from orders.services import create_order
from payments.models import Payment
from payments.services import PaymentError, record_manual_payment

from ..factories import BookFactory, OrderFactory
from ..fakes import stripe_event_payload, stripe_webhook_headers
from ..helpers import format_id, message_levels

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 16)


@pytest.fixture(autouse=True)
def rates(monkeypatch):
    monkeypatch.setattr("currencies.services.today", lambda: TODAY)
    ExchangeRate.objects.create(currency_id="USD", date=TODAY, rate=Decimal("45.4274"))


@pytest.fixture
def order(customer):
    """A USD order: 3 * 14.31 (650 UAH) + 20.00 = 62.93 $."""
    hryvnia_book = BookFactory(price=Decimal("650.00"))
    dollar_book = BookFactory(price=Decimal("20.00"), currency_id="USD")
    return create_order(
        customer,
        {format_id(hryvnia_book): 3, format_id(dollar_book): 1},
        currency="USD",
        full_name="Ann Shevchenko",
        phone="+380671234567",
        address="Kyiv",
    )


def press_pay(client, order):
    return client.post(reverse("payments:pay", args=[order.pk]))


def send_webhook(client, session_id, **session_fields):
    payload = stripe_event_payload("checkout.session.completed", session_id, **session_fields)
    return client.post(
        reverse("payments:webhook", args=["stripe"]),
        data=payload,
        content_type="application/json",
        headers=stripe_webhook_headers(payload),
    )


# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------


# Generated with AI
def test_stripe_is_asked_for_the_order_currency(order, customer_client, fake_stripe):
    press_pay(customer_client, order)

    payment = order.payments.get()
    assert (payment.amount, payment.currency_id) == (Decimal("62.93"), "USD")
    price = fake_stripe.created[0]["params"]["line_items"][0]["price_data"]
    assert (price["currency"], price["unit_amount"]) == ("usd", 6293)


# Generated with AI
def test_webhook_with_the_right_sum_and_currency_pays_the_order(
    order, customer_client, client, fake_stripe, mailoutbox, django_capture_on_commit_callbacks
):
    press_pay(customer_client, order)
    session_id = order.payments.get().external_id
    fake_stripe.pay(session_id)

    with django_capture_on_commit_callbacks(execute=True):
        assert send_webhook(client, session_id).status_code == 200

    order.refresh_from_db()
    assert order.payment_status == Order.PaymentStatus.PAID
    email = mailoutbox[0]
    assert email.subject.endswith("оплату отримано (62,93 $)")
    assert "ми отримали вашу оплату 62,93 $" in email.body
    assert "Сума замовлення: 62,93 $" in email.body


# Generated with AI
@pytest.mark.parametrize(
    "changed", [{"currency": "uah"}, {"amount_total": 100}], ids=["currency", "amount"]
)
def test_webhook_with_another_sum_or_currency_is_not_counted(
    order, customer_client, client, fake_stripe, caplog, changed
):
    press_pay(customer_client, order)
    payment = order.payments.get()
    fake_stripe.pay(payment.external_id)

    with caplog.at_level(logging.ERROR, logger="payments.providers.stripe_checkout"):
        # 200: Stripe must not retry it, the money is checked by a manager
        assert send_webhook(client, payment.external_id, **changed).status_code == 200

    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == Payment.Status.PENDING
    assert order.payment_status == Order.PaymentStatus.UNPAID
    assert f"payment {payment.pk}: paid" in caplog.text


# Generated with AI
def test_return_page_does_not_count_a_session_in_another_currency(
    order, customer_client, fake_stripe
):
    press_pay(customer_client, order)
    payment = order.payments.get()
    fake_stripe.pay(payment.external_id).currency = "eur"  # changed on Stripe's side

    response = customer_client.get(reverse("payments:success"), {"session_id": payment.external_id})

    assert "Оплата підтверджується" in response.text
    payment.refresh_from_db()
    assert payment.status == Payment.Status.PENDING


# Generated with AI
def test_success_page_shows_the_sum_in_the_order_currency(order, customer_client, fake_stripe):
    press_pay(customer_client, order)
    session_id = order.payments.get().external_id
    fake_stripe.pay(session_id)

    response = customer_client.get(reverse("payments:success"), {"session_id": session_id})

    assert "62,93 $" in response.text


# Generated with AI
def test_online_payment_in_a_currency_without_cents_is_refused(
    customer, customer_client, fake_stripe
):
    Currency.objects.create(code="JPY", name="Yen", symbol="¥")
    order = OrderFactory(user=customer, currency_id="JPY", total=Decimal("1500.00"))

    response = customer_client.post(reverse("payments:pay", args=[order.pk]), follow=True)

    assert message_levels(response) == ["error"]
    assert "Онлайн-оплата у JPY недоступна." in response.text
    assert fake_stripe.created == []  # Stripe was not asked
    assert order.payments.get().status == Payment.Status.FAILED


# ---------------------------------------------------------------------------
# Manual payments, admin
# ---------------------------------------------------------------------------


# Generated with AI
def test_manual_payment_is_in_the_order_currency(order):
    payment = record_manual_payment(order.pk, Decimal("20.00"))

    assert payment.currency_id == "USD"
    with pytest.raises(PaymentError, match=r"до сплати лише 42,93 \$, 50,00 \$ — забагато"):
        record_manual_payment(order.pk, Decimal("50.00"))


# Generated with AI
def test_admin_shows_payments_with_their_currency(admin_client, order):
    record_manual_payment(order.pk, Decimal("20.00"))

    change_page = admin_client.get(reverse("admin:orders_order_change", args=[order.pk])).text
    payments_page = admin_client.get(reverse("admin:payments_payment_changelist")).text

    assert "20,00 $" in change_page
    assert "20,00 $" in payments_page
    assert "₴" not in payments_page.split('id="result_list"')[1]


# Generated with AI
def test_admin_manual_payment_over_the_due_sum_names_the_currency(admin_client, order):
    url = reverse("admin:orders_order_change", args=[order.pk])
    page = admin_client.get(url)
    form = page.context["adminform"].form
    data = {
        name: form.initial.get(name) or "" for name in ["status", "full_name", "phone", "address"]
    }
    # The management forms of the inlines as the page has them
    for inline in page.context["inline_admin_formsets"]:
        formset = inline.formset
        data[f"{formset.prefix}-TOTAL_FORMS"] = formset.total_form_count()
        data[f"{formset.prefix}-INITIAL_FORMS"] = formset.initial_form_count()
        if inline.opts.__class__.__name__ == "ManualPaymentInline":
            manual = formset.prefix
    data.update(
        {
            f"{manual}-TOTAL_FORMS": 1,
            f"{manual}-0-amount": "70.00",
            f"{manual}-0-note": "cash",
        }
    )

    response = admin_client.post(url, data)

    assert "До сплати лише 62,93 $, а нові оплати разом дають 70,00 $." in response.text
    assert not order.payments.exists()
