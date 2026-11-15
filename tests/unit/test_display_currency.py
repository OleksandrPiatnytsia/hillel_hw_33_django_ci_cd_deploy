"""The currency switcher and the prices on the site in the chosen currency.

The site is in Ukrainian by default: "14,31 $" (a decimal comma, the symbol
after the number). The rates of every test: 1 USD = 45.4274 UAH,
1 EUR = 50.3379 UAH.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.urls import reverse
from django.utils import translation

from cart.cart import Cart
from currencies.display import (
    SESSION_KEY,
    book_price,
    display_currency,
    format_money,
    request_rates,
)
from currencies.models import Currency, ExchangeRate
from currencies.templatetags.money import money

from ..factories import BookFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 16)


@pytest.fixture(autouse=True)
def rates(monkeypatch):
    monkeypatch.setattr("currencies.services.today", lambda: TODAY)
    ExchangeRate.objects.create(currency_id="USD", date=TODAY, rate=Decimal("45.4274"))
    ExchangeRate.objects.create(currency_id="EUR", date=date(2026, 11, 13), rate=Decimal("50.3379"))


def choose(client, code):
    """Press the currency in the navbar switcher."""
    return client.post(reverse("set_currency"), {"currency": code, "next": "/"})


def request_with(code=None):
    request = RequestFactory().get("/")
    request.session = {SESSION_KEY: code} if code else {}
    return request


# ---------------------------------------------------------------------------
# The switcher
# ---------------------------------------------------------------------------


# Generated with AI
def test_choosing_a_currency_saves_it_and_goes_back(client):
    response = client.post(
        reverse("set_currency"), {"currency": "USD", "next": "/?sort=price&page=2"}
    )

    assert response.status_code == 302
    assert response["Location"] == "/?sort=price&page=2"
    assert client.session[SESSION_KEY] == "USD"


# Generated with AI
@pytest.mark.parametrize("code", ["GBP", "PLN", ""])
def test_a_currency_that_is_not_offered_changes_nothing(client, code):
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")  # no rate: not offered
    choose(client, "USD")

    choose(client, code)

    assert client.session[SESSION_KEY] == "USD"


# Generated with AI
def test_the_switcher_does_not_redirect_to_another_site(client):
    response = client.post(
        reverse("set_currency"), {"currency": "EUR", "next": "https://evil.example/"}
    )

    assert response["Location"] == reverse("books:list")


# Generated with AI
def test_the_switcher_answers_only_post(client):
    assert client.get(reverse("set_currency")).status_code == 405


# Generated with AI
def test_navbar_offers_the_currencies_with_a_rate(client):
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")  # no rate yet
    choose(client, "EUR")

    response = client.get(reverse("books:list"))

    assert [currency.code for currency in response.context["currency_choices"]] == [
        "UAH",
        "EUR",
        "USD",
    ]
    assert "€ EUR" in response.text  # the button shows the current one
    assert 'value="EUR"\n                      class="dropdown-item active"' in response.text


# ---------------------------------------------------------------------------
# display_currency, format_money, book_price
# ---------------------------------------------------------------------------


# Generated with AI
def test_the_default_currency_is_uah():
    assert display_currency(request_with()).code == "UAH"


# Generated with AI
def test_a_currency_turned_off_after_it_was_chosen_falls_back_to_uah():
    Currency.objects.filter(code="USD").update(is_active=False)

    assert display_currency(request_with("USD")).code == "UAH"


# Generated with AI
def test_rates_are_read_once_per_request(django_assert_num_queries):
    request = request_with("USD")
    with django_assert_num_queries(2):  # the rates and the currencies, then cached
        display_currency(request)
        request_rates(request)
    with django_assert_num_queries(0):
        for _ in range(24):
            book_price(request, BookFactory.build(price=Decimal("650"), currency_id="UAH"))


# Generated with AI
@pytest.mark.parametrize(
    ("language", "amount", "code", "expected"),
    [
        ("uk", "14.31", "USD", "14,31 $"),
        ("uk", "650", "UAH", "650,00 ₴"),
        ("en", "14.31", "USD", "$14.31"),
        ("en", "9.5", "EUR", "€9.50"),
        ("en", "650", "UAH", "650.00 ₴"),
    ],
)
def test_format_money(language, amount, code, expected):
    with translation.override(language):
        assert format_money(Decimal(amount), code) == expected


# Generated with AI
def test_money_filter_accepts_a_currency_and_skips_empty_values():
    assert money(Decimal("5"), Currency.objects.get(code="EUR")) == "5,00 €"
    assert money(None, "UAH") == ""


# Generated with AI
def test_book_price_converts_and_keeps_the_original():
    book = BookFactory.build(price=Decimal("650.00"), currency_id="UAH")

    price = book_price(request_with("USD"), book)

    assert (str(price), price.converted, price.original) == ("14,31 $", True, "650,00 ₴")
    assert price.rate_date == TODAY


# Generated with AI
def test_book_price_between_two_foreign_currencies_shows_the_newer_rate_date():
    book = BookFactory.build(price=Decimal("10.00"), currency_id="EUR")

    price = book_price(request_with("USD"), book)

    assert str(price) == "11,08 $"  # 10 * 50.3379 / 45.4274
    assert price.rate_date == TODAY  # USD 16.11, EUR 13.11


# Generated with AI
def test_book_price_in_its_own_currency_is_not_converted():
    price = book_price(
        request_with("USD"), BookFactory.build(price=Decimal("20"), currency_id="USD")
    )

    assert (str(price), price.converted, price.rate_date) == ("20,00 $", False, None)


# Generated with AI
def test_a_book_in_a_currency_without_a_rate_keeps_its_own_currency():
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")
    book = BookFactory.build(price=Decimal("40"), currency_id="PLN")

    assert str(book_price(request_with("USD"), book)) == "40,00 zł"


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@pytest.fixture
def mixed_books():
    return [
        BookFactory(title="Hryvnia book", price=Decimal("650.00")),  # 14.31 USD
        BookFactory(title="Dollar book", price=Decimal("20.00"), currency_id="USD"),
        BookFactory(title="Euro book", price=Decimal("10.00"), currency_id="EUR"),  # 11.08 USD
    ]


# Generated with AI
def test_catalog_shows_and_sorts_prices_in_the_chosen_currency(client, mixed_books):
    choose(client, "USD")

    response = client.get(reverse("books:list"), {"sort": "price"})

    assert [book.title for book in response.context["books"]] == [
        "Euro book",
        "Hryvnia book",
        "Dollar book",
    ]
    for text in ("11,08 $", "14,31 $", "20,00 $"):
        assert text in response.text
    assert "₴" not in response.text.split("<main")[1]  # no hryvnias in the page body


# Generated with AI
def test_catalog_price_filter_is_in_the_chosen_currency(client, mixed_books):
    choose(client, "USD")

    response = client.get(reverse("books:list"), {"price_min": "11.08", "price_max": "14.31"})

    assert sorted(book.title for book in response.context["books"]) == [
        "Euro book",
        "Hryvnia book",
    ]
    assert response.context["filter_form"]["price_min"].label == "Ціна від, $"


# Generated with AI
def test_catalog_price_slider_spans_the_whole_catalog_in_the_chosen_currency(client, mixed_books):
    choose(client, "USD")

    # The filter narrows the list, not the slider: its scale stays
    response = client.get(reverse("books:list"), {"price_max": "12"})

    # 11.08 .. 20.00 USD, whole numbers outward
    assert response.context["price_range"] == {"min": 11, "max": 20}
    assert [book.title for book in response.context["books"]] == ["Euro book"]
    assert 'data-min="11" data-max="20"' in response.text
    assert "Ціна, $" in response.text  # one label for "from" and "to"


# Generated with AI
def test_catalog_has_no_price_slider_when_all_books_cost_the_same(client):
    BookFactory(price=Decimal("100.00"))
    BookFactory(price=Decimal("100.00"))

    response = client.get(reverse("books:list"))

    assert response.context["price_range"] is None
    assert "price-slider" not in response.text
    assert 'name="price_min"' in response.text  # the fields stay


# Generated with AI
def test_book_page_shows_the_original_price_and_the_rate_date(client, mixed_books):
    choose(client, "USD")

    response = client.get(mixed_books[0].get_absolute_url())

    assert "14,31 $" in response.text
    assert "650,00 ₴ за курсом НБУ на 16.11.2026" in response.text


# Generated with AI
def test_book_page_in_the_books_own_currency_has_no_note(client, mixed_books):
    response = client.get(mixed_books[0].get_absolute_url())

    assert "650,00 ₴" in response.text
    assert "за курсом НБУ" not in response.text


# Generated with AI
def test_author_page_shows_prices_in_the_chosen_currency(client, mixed_books):
    choose(client, "EUR")

    response = client.get(mixed_books[1].author.get_absolute_url())

    assert "18,05 €" in response.text  # 20 USD


# Generated with AI
def test_cart_is_in_the_chosen_currency(client, mixed_books):
    hryvnia_book, dollar_book, _euro_book = mixed_books
    client.post(reverse("cart:add", args=[hryvnia_book.pk]), {"quantity": 3})
    client.post(reverse("cart:add", args=[dollar_book.pk]), {"quantity": 1})
    choose(client, "USD")

    response = client.get(reverse("cart:detail"))

    cart = response.context["cart"]
    assert cart.currency.code == "USD"
    # The price of one copy is rounded first: 3 * 14.31, not 1950 / 45.4274
    assert [(item["price"], item["cost"]) for item in cart] == [
        (Decimal("14.31"), Decimal("42.93")),
        (Decimal("20.00"), Decimal("20.00")),
    ]
    assert cart.total == Decimal("62.93")
    assert "62,93 $" in response.text


# Generated with AI
def test_cart_object_follows_the_session_currency(mixed_books):
    request = request_with("EUR")
    request.session = {SESSION_KEY: "EUR", "cart": {str(mixed_books[1].pk): {"quantity": 2}}}

    cart = Cart(request)

    assert (cart.currency.code, cart.total) == ("EUR", Decimal("36.10"))  # 2 * 18.05
