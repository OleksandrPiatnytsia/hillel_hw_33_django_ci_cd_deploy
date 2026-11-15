"""Stage 4 of the currencies: the order currency.

The currency is chosen once, at checkout (the one the cart is shown in),
and never changes. Every book is converted at the rate of that day; the
order keeps the rates, so it doesn't change when the rates do. Reports add
up orders of different currencies in UAH.

The rates of every test: 1 USD = 45.4274 UAH, 1 EUR = 50.3379 UAH.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from currencies.models import Currency, ExchangeRate
from currencies.services import clear_rates_cache
from inventory.models import Stock
from orders.models import Order
from orders.reports import build_daily_report
from orders.services import CROSS_RATE_PLACES, OrderError, create_order

from ..factories import BookFactory, UserFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 16)
USD_RATE = Decimal("45.4274")
EUR_RATE = Decimal("50.3379")
DELIVERY = {"full_name": "Ann Shevchenko", "phone": "+380671234567", "address": "Kyiv"}


@pytest.fixture(autouse=True)
def rates(monkeypatch):
    monkeypatch.setattr("currencies.services.today", lambda: TODAY)
    ExchangeRate.objects.create(currency_id="USD", date=TODAY, rate=USD_RATE)
    ExchangeRate.objects.create(currency_id="EUR", date=TODAY, rate=EUR_RATE)


@pytest.fixture
def books():
    return {
        "hryvnia": BookFactory(title="Hryvnia book", price=Decimal("650.00")),  # 14.31 USD
        "dollar": BookFactory(title="Dollar book", price=Decimal("20.00"), currency_id="USD"),
        "euro": BookFactory(title="Euro book", price=Decimal("10.00"), currency_id="EUR"),
    }


def order_in(currency, books, user=None):
    return create_order(
        user or UserFactory(),
        {books["hryvnia"].pk: 3, books["dollar"].pk: 1, books["euro"].pk: 1},
        currency=currency,
        **DELIVERY,
    )


# ---------------------------------------------------------------------------
# create_order()
# ---------------------------------------------------------------------------


# Generated with AI
def test_order_in_dollars_converts_every_book(books):
    order = order_in("USD", books)

    assert (order.currency_id, order.exchange_rate) == ("USD", USD_RATE)
    items = {item.title: item for item in order.items.all()}
    # The price of ONE copy is rounded first, then multiplied: 3 * 14.31
    assert [(title, item.price, item.cost) for title, item in sorted(items.items())] == [
        ("Dollar book", Decimal("20.00"), Decimal("20.00")),
        ("Euro book", Decimal("11.08"), Decimal("11.08")),  # 10 * 50.3379 / 45.4274
        ("Hryvnia book", Decimal("14.31"), Decimal("42.93")),
    ]
    assert order.total == Decimal("74.01")
    assert order.total_uah == (Decimal("74.01") * USD_RATE).quantize(Decimal("0.01"))


# Generated with AI
def test_order_items_keep_the_original_price_and_the_rate(books):
    order = order_in("USD", books)

    hryvnia = order.items.get(title="Hryvnia book")
    assert (hryvnia.original_price, hryvnia.original_currency_id) == (Decimal("650.00"), "UAH")
    assert hryvnia.exchange_rate == (1 / USD_RATE).quantize(CROSS_RATE_PLACES)
    dollar = order.items.get(title="Dollar book")
    assert (dollar.original_currency_id, dollar.exchange_rate) == ("USD", Decimal("1"))


# Generated with AI
def test_order_in_hryvnias_is_as_before(books):
    order = order_in("UAH", books)

    assert (order.currency_id, order.exchange_rate) == ("UAH", Decimal("1"))
    # 3 * 650 + 20 * 45.4274 + 10 * 50.3379
    assert order.total == Decimal("1950.00") + Decimal("908.55") + Decimal("503.38")
    assert order.total_uah == order.total


# Generated with AI
def test_the_order_does_not_change_when_the_rates_do(books, client):
    order = order_in("USD", books)
    ExchangeRate.objects.filter(currency_id="USD").update(rate=Decimal("50"))
    clear_rates_cache()

    order.refresh_from_db()
    assert (order.total, order.exchange_rate) == (Decimal("74.01"), USD_RATE)
    client.force_login(order.user)
    assert "74,01 $" in client.get(order.get_absolute_url()).text


# Generated with AI
@pytest.mark.parametrize("code", ["GBP", "PLN"])
def test_a_currency_that_is_not_offered_is_rejected_and_nothing_is_reserved(books, code):
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")  # no rate: not offered

    with pytest.raises(OrderError, match=f"Замовлення у {code} не приймаються"):
        order_in(code, books)

    assert not Order.objects.exists()
    assert Stock.objects.get(book=books["hryvnia"]).quantity == 10


# Generated with AI
def test_a_book_in_a_currency_without_a_rate_cannot_be_ordered():
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")
    book = BookFactory(title="Zloty book", price=Decimal("40"), currency_id="PLN")

    with pytest.raises(OrderError, match="немає курсу PLN"):
        create_order(UserFactory(), {book.pk: 1}, **DELIVERY)

    assert not Order.objects.exists()


# ---------------------------------------------------------------------------
# The checkout page
# ---------------------------------------------------------------------------


@pytest.fixture
def shopper(client, customer, books):
    client.force_login(customer)
    client.post(reverse("cart:add", args=[books["hryvnia"].pk]), {"quantity": 3})
    client.post(reverse("cart:add", args=[books["dollar"].pk]), {"quantity": 1})
    client.post(reverse("set_currency"), {"currency": "USD", "next": "/"})
    return client


# Generated with AI
def test_checkout_is_in_the_currency_of_the_switcher(shopper):
    response = shopper.get(reverse("orders:checkout"))

    assert response.context["form"].initial["currency"] == "USD"
    assert '<input type="hidden" name="currency" value="USD"' in response.text
    assert "62,93 $" in response.text  # 3 * 14.31 + 20
    assert '<option value="USD" selected>' in response.text  # the currency select


# Generated with AI
def test_checkout_makes_the_order_in_the_currency_the_page_showed(shopper):
    response = shopper.post(reverse("orders:checkout"), {**DELIVERY, "currency": "USD"})

    order = Order.objects.get()
    assert response["Location"] == order.get_absolute_url()
    assert (order.currency_id, order.total) == ("USD", Decimal("62.93"))
    page = shopper.get(order.get_absolute_url()).text
    assert "14,31 $" in page
    assert "650,00 ₴" in page  # the original price under the converted one
    assert "Оплатити 62,93 $" in page


# Generated with AI
def test_the_hidden_currency_wins_over_the_switcher_changed_in_another_tab(shopper):
    shopper.post(reverse("set_currency"), {"currency": "EUR", "next": "/"})

    shopper.post(reverse("orders:checkout"), {**DELIVERY, "currency": "USD"})

    assert Order.objects.get().currency_id == "USD"


# Generated with AI
def test_checkout_without_the_currency_field_uses_the_cart_currency(shopper):
    shopper.post(reverse("orders:checkout"), DELIVERY)

    assert Order.objects.get().currency_id == "USD"


# Generated with AI
def test_checkout_with_a_currency_turned_off_meanwhile_shows_an_error(shopper):
    Currency.objects.filter(code="USD").update(is_active=False)
    clear_rates_cache()

    response = shopper.post(reverse("orders:checkout"), {**DELIVERY, "currency": "USD"})

    assert response.status_code == 200
    assert "Ця валюта більше не приймається, оберіть іншу." in response.text
    assert not Order.objects.exists()


# Generated with AI
def test_order_email_is_in_the_order_currency(
    shopper, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        shopper.post(reverse("orders:checkout"), {**DELIVERY, "currency": "USD"})

    email = mailoutbox[0]
    assert email.subject.endswith("створено (62,93 $)")
    assert "Hryvnia book: 3 x 14,31 $ = 42,93 $" in email.body
    assert "Разом: 62,93 $" in email.body


# ---------------------------------------------------------------------------
# Reports, admin, commands
# ---------------------------------------------------------------------------


# Generated with AI
def test_daily_report_adds_up_the_orders_in_hryvnias(books):
    dollar_order = create_order(UserFactory(), {books["dollar"].pk: 2}, currency="USD", **DELIVERY)
    hryvnia_order = create_order(UserFactory(), {books["hryvnia"].pk: 1}, **DELIVERY)

    report = build_daily_report(timezone.localdate(dollar_order.created_at))

    # 2 * 20 USD = 1817.10 UAH at the rate of the order + 650 UAH
    assert report.revenue == Decimal("1817.10") + Decimal("650.00")
    assert {book["title"]: book["revenue"] for book in report.top_books} == {
        "Dollar book": Decimal("1817.10"),
        "Hryvnia book": Decimal("650.00"),
    }
    orders_csv = report.csv_files()[0][1].decode("utf-8-sig")
    assert orders_csv.splitlines()[0].endswith("payment_status,currency,total,total_uah")
    assert f"{dollar_order.pk}," in orders_csv and ",USD,40.00,1817.10" in orders_csv
    assert hryvnia_order.total_uah == Decimal("650.00")


# Generated with AI
def test_admin_shows_the_amounts_with_the_order_currency(admin_client, books):
    order = order_in("USD", books)

    change_page = admin_client.get(reverse("admin:orders_order_change", args=[order.pk])).text
    list_page = admin_client.get(reverse("admin:orders_order_changelist")).text

    assert "74,01 $" in change_page
    assert "42,93 $" in change_page  # the cost of the item
    assert "650,00 ₴" in change_page  # its original price
    assert "45,427400" in change_page  # the rate of the order
    assert "74,01 $" in list_page


# Generated with AI
def test_cancel_unpaid_dry_run_shows_the_order_currency(books, capsys):
    order = order_in("USD", books)
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=30))

    call_command("cancel_unpaid_orders", "--dry-run")

    assert "74,01 $" in capsys.readouterr().out
