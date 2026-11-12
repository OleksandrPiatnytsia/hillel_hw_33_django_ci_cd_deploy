"""Integration: the site, the messages and the emails in both languages.

These tests read the compiled translations (locale/uk/LC_MESSAGES/django.mo):
if compilemessages was not run after a change of the .po file, they fail.
"""

from decimal import Decimal

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import translation

from orders.models import Order

from ..factories import BookFactory, OrderFactory, UserFactory
from ..fakes import stripe_event_payload, stripe_webhook_headers

pytestmark = pytest.mark.django_db

COOKIE = settings.LANGUAGE_COOKIE_NAME
DELIVERY = {"full_name": "Ann Shevchenko", "phone": "+380671234567", "address": "Kyiv"}


def page(client, url, language, **params):
    client.cookies[COOKIE] = language
    return client.get(url, params).content.decode()


@pytest.mark.parametrize(
    ("language", "texts"),
    [
        ("uk", ["Каталог", "Кошик", "Увійти", "Книгарня", "Фільтри"]),
        ("en", ["Catalog", "Cart", "Log in", "Bookstore", "Filters"]),
    ],
)
def test_catalog_page_in_both_languages(client, language, texts):
    html = page(client, reverse("books:list"), language)

    for text in texts:
        assert text in html


@pytest.mark.parametrize(
    ("count", "uk_text", "en_text"),
    [
        (1, "Знайдено: 1 книга", "Found: 1 book"),
        (3, "Знайдено: 3 книги", "Found: 3 books"),
        (5, "Знайдено: 5 книг", "Found: 5 books"),
        (11, "Знайдено: 11 книг", "Found: 11 books"),
        (21, "Знайдено: 21 книга", "Found: 21 books"),
    ],
)
def test_plural_forms_of_books_found(client, count, uk_text, en_text):
    BookFactory.create_batch(count)

    assert uk_text in page(client, reverse("books:list"), "uk")
    assert en_text in page(client, reverse("books:list"), "en")


def test_low_stock_badge_uses_ukrainian_plural(client):
    book = BookFactory(stock=3)

    assert "Залишилося 3 примірники" in page(client, book.get_absolute_url(), "uk")


def test_form_labels_come_from_translated_model_fields(customer, customer_client):
    customer_client.post(reverse("cart:add", args=[BookFactory().pk]), {"quantity": 1})

    html = page(customer_client, reverse("orders:checkout"), "uk")

    assert "Ім&#x27;я та прізвище" in html  # Order.full_name verbose_name
    assert "Адреса доставки" in html
    assert "Зберегти телефон і адресу в моєму профілі" in html


def test_flash_message_in_the_language_of_the_request(client):
    book = BookFactory(title="Кобзар")
    client.cookies[COOKIE] = "uk"

    response = client.post(reverse("cart:add", args=[book.pk]), {"quantity": 1}, follow=True)

    assert "«Кобзар»: у кошику 1." in response.content.decode()


def test_order_str_and_status_labels_follow_active_language():
    order = OrderFactory.build(pk=7, status=Order.Status.SHIPPED)

    with translation.override("uk"):
        assert str(order) == "Замовлення #7"
        assert order.get_status_display() == "Відправлено"
    with translation.override("en"):
        assert str(order) == "Order #7"
        assert order.get_status_display() == "Shipped"


# ---------------------------------------------------------------------------
# Emails: in the recipient's language, not in the language of the request
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("user_language", "subject_start", "body_text"),
    [
        ("uk", "Книгарня: Замовлення #", "Дякуємо за замовлення."),
        ("en", "Bookstore: Order #", "Thank you for your order."),
    ],
)
def test_order_email_in_users_language_whatever_the_site_language(
    client, mailoutbox, django_capture_on_commit_callbacks, user_language, subject_start, body_text
):
    user = UserFactory(language=user_language)
    client.force_login(user)
    # The site is in the OTHER language at the moment of the checkout
    client.cookies[COOKIE] = "en" if user_language == "uk" else "uk"
    client.post(reverse("cart:add", args=[BookFactory().pk]), {"quantity": 1})

    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("orders:checkout"), DELIVERY)

    email = mailoutbox[0]
    assert email.subject.startswith(subject_start)
    assert body_text in email.body
    html, _mimetype = email.alternatives[0]
    assert f'<html lang="{user_language}">' in html


def test_payment_email_from_webhook_is_in_users_language(
    client, fake_stripe, mailoutbox, django_capture_on_commit_callbacks
):
    """The webhook request comes from Stripe: no user, no cookie, the
    default language. The email still follows User.language."""
    user = UserFactory(language="en")
    order = OrderFactory(user=user, items=[(BookFactory(price=Decimal("100.00")), 1)])
    user_client = Client()  # the customer's browser; `client` plays Stripe
    user_client.force_login(user)
    user_client.post(reverse("payments:pay", args=[order.pk]))
    session_id = order.payments.get().external_id
    fake_stripe.pay(session_id)
    payload = stripe_event_payload("checkout.session.completed", session_id)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            reverse("payments:webhook", args=["stripe"]),
            data=payload,
            content_type="application/json",
            headers={**stripe_webhook_headers(payload), "Accept-Language": "uk"},
        )

    assert mailoutbox[0].subject.startswith("Bookstore: payment for Order #")


# ---------------------------------------------------------------------------
# Stripe page language
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("site_language", "stripe_locale"), [("en", "en"), ("uk", "auto")])
def test_stripe_page_language_follows_the_site(
    customer, customer_client, fake_stripe, site_language, stripe_locale
):
    order = OrderFactory(user=customer, items=[(BookFactory(), 1)])
    customer_client.cookies[COOKIE] = site_language

    customer_client.post(reverse("payments:pay", args=[order.pk]))

    params = fake_stripe.created[0]["params"]
    assert params["locale"] == stripe_locale
    product = params["line_items"][0]["price_data"]["product_data"]["name"]
    assert product == (
        "Bookstore: order #" if site_language == "en" else "Книгарня: замовлення #"
    ) + str(order.pk)


# ---------------------------------------------------------------------------
# The emails of the background tasks (hw_31): every one in the recipient's
# language, without English pieces of untranslated texts
# ---------------------------------------------------------------------------

# Words of the English templates that a Ukrainian email must not contain
ENGLISH = [
    "Bookstore",
    "Hello",
    "Total",
    "UAH",
    "Order page",
    "was not paid",
    "If you still",
    "report for",
    "Sales report",
    "Orders:",
    "Best sellers",
    "Low stock",
    "Details",
]
# Not "left" alone: the HTML part has align="left"; "2 left" is checked below


def _all_texts(message):
    # The report is a plain EmailMessage (text + CSV files), no HTML part
    html = [part.content for part in getattr(message, "alternatives", [])]
    return " ".join([message.subject, message.body, *html])


# Generated with AI
@pytest.mark.parametrize("language", ["uk", "en"])
def test_task_emails_are_in_the_language_of_the_recipient(language, mailoutbox):
    from orders.emails import send_order_cancelled_email, send_order_created_email
    from orders.reports import build_daily_report, send_daily_report_email

    customer = UserFactory(language=language)
    UserFactory(language=language, groups=["Managers"])
    book = BookFactory(title="Kobzar", stock=2)  # low stock: that part of the report too
    order = OrderFactory(user=customer, items=[(book, 1)])

    send_order_created_email(order.pk)
    send_order_cancelled_email(order.pk)
    send_daily_report_email(build_daily_report(order.created_at.date()))

    assert len(mailoutbox) == 3
    texts = [_all_texts(message) for message in mailoutbox]
    if language == "uk":
        for text in texts:
            assert [word for word in ENGLISH if word in text] == []
        assert "скасовано" in mailoutbox[1].subject
        assert "звіт за" in mailoutbox[2].subject
        assert "Мало на складі: 1 книга." in mailoutbox[2].body
        assert "Kobzar: залишилось 2" in mailoutbox[2].body
    else:
        assert "is cancelled" in mailoutbox[1].subject
        assert "Low stock: 1 book." in mailoutbox[2].body
