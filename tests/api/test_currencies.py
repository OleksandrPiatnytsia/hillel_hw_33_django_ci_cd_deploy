"""Stage 6 of the currencies: the API.

    GET /api/currencies/              the currencies offered, with today's rate
    GET /api/books/?currency=USD      display_price in dollars; the price
                                      filters and ?ordering=price use it
    POST /api/formats/ {"currency"}   the currency of the format's price
    POST /api/orders/ {"currency"}    the currency of the order

The rates of every test: 1 USD = 45.4274 UAH, 1 EUR = 50.3379 UAH.
"""

from datetime import date
from decimal import Decimal

import pytest

from currencies.models import Currency, ExchangeRate
from orders.models import Order
from tests.factories import BookFactory, UserFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 16)


@pytest.fixture(autouse=True)
def rates(monkeypatch):
    monkeypatch.setattr("currencies.services.today", lambda: TODAY)
    ExchangeRate.objects.create(currency_id="USD", date=TODAY, rate=Decimal("45.4274"))
    ExchangeRate.objects.create(currency_id="EUR", date=date(2026, 11, 13), rate=Decimal("50.3379"))


@pytest.fixture
def books():
    return [
        BookFactory(title="Hryvnia book", price=Decimal("650.00")),  # 14.31 USD
        BookFactory(title="Dollar book", price=Decimal("20.00"), currency_id="USD"),
        BookFactory(title="Euro book", price=Decimal("10.00"), currency_id="EUR"),  # 11.08 USD
    ]


def titles(response):
    return [book["title"] for book in response.json()["results"]]


# ---------------------------------------------------------------------------
# /api/currencies/
# ---------------------------------------------------------------------------


# Generated with AI
def test_currencies_list_has_the_offered_ones_with_their_rates(api_client):
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")  # no rate: not offered

    response = api_client.get("/api/currencies/")

    assert response.status_code == 200
    assert [
        (currency["code"], currency["symbol"], currency["rate"], currency["rate_date"])
        for currency in response.json()
    ] == [
        ("UAH", "₴", "1.000000", None),
        ("EUR", "€", "50.337900", "2026-11-13"),
        ("USD", "$", "45.427400", "2026-11-16"),
    ]


# Generated with AI
def test_one_currency_by_its_code_and_404_for_others(api_client):
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")

    assert api_client.get("/api/currencies/usd/").json()["rate"] == "45.427400"
    assert api_client.get("/api/currencies/PLN/").status_code == 404
    assert api_client.get("/api/currencies/XYZ/").status_code == 404


# ---------------------------------------------------------------------------
# Books
# ---------------------------------------------------------------------------


# Generated with AI
def test_books_have_their_price_currency_and_the_price_in_uah(api_client, books):
    response = api_client.get("/api/books/", {"ordering": "title"})

    assert [
        (
            book["formats"][0]["price"],
            book["formats"][0]["currency"],
            book["display_price"],
            book["display_currency"],
        )
        for book in response.json()["results"]
    ] == [
        ("20.00", "USD", "908.55", "UAH"),
        ("10.00", "EUR", "503.38", "UAH"),
        ("650.00", "UAH", "650.00", "UAH"),
    ]


# Generated with AI
def test_books_in_the_currency_of_the_parameter_sorted_by_it(api_client, books):
    response = api_client.get("/api/books/", {"currency": "usd", "ordering": "price"})

    assert titles(response) == ["Euro book", "Hryvnia book", "Dollar book"]
    assert [book["display_price"] for book in response.json()["results"]] == [
        "11.08",
        "14.31",
        "20.00",
    ]
    assert {book["display_currency"] for book in response.json()["results"]} == {"USD"}


# Generated with AI
def test_books_without_a_rate_go_last_in_both_directions(api_client, books):
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")
    BookFactory(title="Zloty book", price=Decimal("1.00"), currency_id="PLN")

    ascending = api_client.get("/api/books/", {"currency": "USD", "ordering": "price"})
    descending = api_client.get("/api/books/", {"currency": "USD", "ordering": "-price"})

    assert titles(ascending)[-1] == titles(descending)[-1] == "Zloty book"
    assert titles(descending)[:3] == ["Dollar book", "Hryvnia book", "Euro book"]
    assert ascending.json()["results"][-1]["display_price"] is None


# Generated with AI
def test_price_filters_are_in_the_currency_of_the_parameter(api_client, books):
    response = api_client.get(
        "/api/books/", {"currency": "USD", "price_min": "11.08", "price_max": "14.31"}
    )

    assert sorted(titles(response)) == ["Euro book", "Hryvnia book"]


# Generated with AI
@pytest.mark.parametrize("code", ["GBP", "PLN"])
def test_a_currency_that_is_not_offered_is_400(api_client, books, code):
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")

    response = api_client.get("/api/books/", {"currency": code})

    assert response.status_code == 400
    # The API answers in the language of the site (Ukrainian by default)
    assert response.json()["currency"] == [
        f"Валюта «{code}» недоступна. Оберіть одну з: UAH, EUR, USD."
    ]


# Generated with AI
def test_one_book_in_the_currency_of_the_parameter(api_client, books):
    response = api_client.get(f"/api/books/{books[0].pk}/", {"currency": "EUR"})

    assert (response.json()["display_price"], response.json()["display_currency"]) == (
        "12.91",  # 650 / 50.3379
        "EUR",
    )


# Generated with AI
def test_editor_creates_a_format_priced_in_dollars(as_user, editor):
    book = BookFactory(formats=False)

    response = as_user(editor).post(
        "/api/formats/?currency=UAH",
        {"book_id": book.pk, "format_type": "ebook", "price": "20.00", "currency": "USD"},
        format="json",
    )

    assert response.status_code == 201
    assert book.formats.get().currency_id == "USD"
    assert (response.json()["currency"], response.json()["display_price"]) == ("USD", "908.55")


# Generated with AI
def test_a_new_format_without_a_currency_is_in_hryvnias(as_user, editor):
    book = BookFactory(formats=False)

    response = as_user(editor).post(
        "/api/formats/", {"book_id": book.pk, "format_type": "ebook", "price": "250.00"}
    )

    assert response.json()["currency"] == "UAH"


# Generated with AI
def test_changing_the_price_answers_with_the_new_display_price(as_user, editor, books):
    paper = books[1].formats.get()

    response = as_user(editor).patch(
        f"/api/formats/{paper.pk}/?currency=USD", {"price": "25.00"}, format="json"
    )
    book = as_user(editor).get(f"/api/books/{books[1].pk}/", {"currency": "USD"}).json()

    assert response.json()["display_price"] == "25.00"
    # The price "from" of the book follows its format
    assert book["display_price"] == "25.00"


# Generated with AI
def test_a_turned_off_currency_only_for_a_format_that_has_it(as_user, editor, books):
    Currency.objects.filter(code="EUR").update(is_active=False)
    client = as_user(editor)
    euro, hryvnia = books[2].formats.get(), books[0].formats.get()

    kept = client.patch(f"/api/formats/{euro.pk}/", {"currency": "EUR"}, format="json")
    refused = client.patch(f"/api/formats/{hryvnia.pk}/", {"currency": "EUR"}, format="json")
    unknown = client.patch(f"/api/formats/{hryvnia.pk}/", {"currency": "GBP"}, format="json")

    assert kept.status_code == 200
    assert refused.status_code == unknown.status_code == 400
    assert refused.json()["currency"] == ["Валюту EUR вимкнено."]


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def order_data(books, **changes):
    return {
        "full_name": "Ann Shevchenko",
        "phone": "+380671234567",
        "address": "Kyiv",
        "items": [{"book_id": books[0].pk, "quantity": 3}, {"book_id": books[1].pk, "quantity": 1}],
        **changes,
    }


# Generated with AI
def test_order_in_dollars(as_user, books):
    response = as_user(UserFactory()).post(
        "/api/orders/", order_data(books, currency="USD"), format="json"
    )

    assert response.status_code == 201
    order = response.json()
    assert (order["currency"], order["exchange_rate"], order["total"]) == (
        "USD",
        "45.427400",
        "62.93",  # 3 * 14.31 + 20.00
    )
    assert order["amount_due"] == "62.93"
    assert [
        (item["price"], item["original_price"], item["original_currency"])
        for item in order["items"]
    ] == [("14.31", "650.00", "UAH"), ("20.00", "20.00", "USD")]


# Generated with AI
def test_order_without_a_currency_is_in_hryvnias(as_user, books):
    response = as_user(UserFactory()).post("/api/orders/", order_data(books), format="json")

    assert (response.json()["currency"], response.json()["total"]) == ("UAH", "2858.55")


# Generated with AI
def test_order_in_a_currency_that_is_not_offered_is_400(as_user, books):
    response = as_user(UserFactory()).post(
        "/api/orders/", order_data(books, currency="GBP"), format="json"
    )

    assert response.status_code == 400
    assert response.json()["currency"] == [
        "Валюта «GBP» недоступна. Оберіть одну з: UAH, EUR, USD."
    ]
    assert not Order.objects.exists()


# Generated with AI
def test_the_same_idempotency_key_with_another_currency_is_422(as_user, books):
    client = as_user(UserFactory())
    headers = {"Idempotency-Key": "order-1"}

    first = client.post(
        "/api/orders/", order_data(books, currency="USD"), format="json", headers=headers
    )
    again = client.post(
        "/api/orders/", order_data(books, currency="USD"), format="json", headers=headers
    )
    other = client.post(
        "/api/orders/", order_data(books, currency="EUR"), format="json", headers=headers
    )

    assert (first.status_code, again.status_code, other.status_code) == (201, 201, 422)
    assert Order.objects.count() == 1


# Generated with AI
def test_orders_filtered_by_currency(as_user, books):
    client = as_user(UserFactory())
    client.post("/api/orders/", order_data(books, currency="USD"), format="json")
    client.post("/api/orders/", order_data(books), format="json")

    response = client.get("/api/orders/", {"currency": "USD"})

    assert [order["currency"] for order in response.json()["results"]] == ["USD"]


# Generated with AI
def test_the_docs_describe_the_currency_parameter_and_endpoint(api_client):
    schema = api_client.get("/api/schema/", {"format": "json"}).json()

    book_parameters = [
        parameter["name"] for parameter in schema["paths"]["/api/books/"]["get"]["parameters"]
    ]
    assert "currency" in book_parameters
    assert "/api/currencies/" in schema["paths"]
    assert "currency" in schema["components"]["schemas"]["OrderCreateRequest"]["properties"]


# Generated with AI
def test_a_format_in_a_currency_without_a_rate_has_no_display_price(as_user, editor):
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")  # active, no rate yet
    book = BookFactory(formats=False)

    response = as_user(editor).post(
        "/api/formats/",
        {"book_id": book.pk, "format_type": "paper", "price": "40.00", "currency": "PLN"},
        format="json",
    )
    answer = as_user(editor).get(f"/api/books/{book.pk}/").json()

    assert response.status_code == 201
    assert response.json()["display_price"] is None
    assert answer["display_price"] is None


# Generated with AI
def test_the_schema_is_built_without_the_rates(api_client, monkeypatch):
    """check --deploy builds the schema without Redis (CI): no rates may be read."""

    def no_cache():
        raise ConnectionError("Redis is not available (test)")

    monkeypatch.setattr("currencies.services.current_rates", no_cache)

    assert api_client.get("/api/schema/").status_code == 200
