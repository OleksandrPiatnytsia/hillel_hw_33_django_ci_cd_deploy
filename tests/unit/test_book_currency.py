"""The currency of a book's price (Book.currency) and prices in one currency in SQL."""

from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.db.models import Avg
from django.db.models.deletion import ProtectedError
from django.urls import reverse

from books.forms import BookForm
from books.models import Book, Category
from currencies.models import Currency, ExchangeRate
from currencies.services import RateUnavailable, convert, price_in

from ..factories import AuthorFactory, BookFactory, CategoryFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 16)


@pytest.fixture(autouse=True)
def rates(monkeypatch):
    """16.11.2026: 1 USD = 45.4274 UAH, 1 EUR = 50.3379 UAH."""
    monkeypatch.setattr("currencies.services.today", lambda: TODAY)
    ExchangeRate.objects.create(currency_id="USD", date=TODAY, rate=Decimal("45.4274"))
    ExchangeRate.objects.create(currency_id="EUR", date=TODAY, rate=Decimal("50.3379"))


def form_data(**changes):
    data = {
        "title": "Kobzar",
        "author": AuthorFactory().pk,
        "price": "20.00",
        "currency": "USD",
        "stock": "1",
        "description": "",
    }
    return {**data, **changes}


# ---------------------------------------------------------------------------
# The field
# ---------------------------------------------------------------------------


# Generated with AI
def test_a_new_book_is_in_hryvnias_by_default():
    assert BookFactory().currency_id == "UAH"


# Generated with AI
def test_a_currency_with_books_cannot_be_deleted():
    BookFactory(currency_id="USD")
    with pytest.raises(ProtectedError):
        Currency.objects.get(code="USD").delete()


# Generated with AI
def test_book_form_saves_the_currency():
    form = BookForm(data=form_data())

    assert form.is_valid(), form.errors
    assert form.save().currency_id == "USD"


# Generated with AI
def test_book_form_offers_active_currencies_with_uah_preselected():
    Currency.objects.filter(code="EUR").update(is_active=False)

    form = BookForm()

    choices = [label for _value, label in form.fields["currency"].choices]
    assert choices == ["UAH (₴)", "USD ($)"]  # no empty "------" choice
    assert form["currency"].value() == "UAH"


# Generated with AI
def test_book_form_keeps_the_turned_off_currency_of_the_book():
    book = BookFactory(currency_id="EUR")
    Currency.objects.filter(code="EUR").update(is_active=False)

    form = BookForm(instance=book)

    assert "EUR (€)" in [label for _value, label in form.fields["currency"].choices]


# Generated with AI
def test_book_form_refuses_a_turned_off_currency_for_another_book():
    Currency.objects.filter(code="EUR").update(is_active=False)

    form = BookForm(data=form_data(currency="EUR"))

    assert "currency" in form.errors


# Generated with AI
def test_admin_book_list_shows_and_filters_the_currency(admin_client):
    BookFactory(title="In dollars", currency_id="USD")
    BookFactory(title="In hryvnias")

    response = admin_client.get(
        reverse("admin:books_book_changelist") + "?currency__code__exact=USD"
    )

    assert response.status_code == 200
    assert [book.title for book in response.context["cl"].result_list] == ["In dollars"]
    assert 'field-currency nowrap">USD</td>' in response.text


# ---------------------------------------------------------------------------
# price_in(): a price in one currency, calculated by the database
# ---------------------------------------------------------------------------


@pytest.fixture
def mixed_books():
    BookFactory(title="650 UAH", price=Decimal("650.00"))  # 14.31 USD
    BookFactory(title="20 USD", price=Decimal("20.00"), currency_id="USD")
    BookFactory(title="10 EUR", price=Decimal("10.00"), currency_id="EUR")  # 11.08 USD


# Generated with AI
def test_price_in_sorts_books_of_different_currencies(mixed_books):
    books = Book.objects.annotate(usd=price_in("USD")).order_by("usd")

    assert [(book.title, book.usd) for book in books] == [
        ("10 EUR", Decimal("11.08")),
        ("650 UAH", Decimal("14.31")),
        ("20 USD", Decimal("20.00")),
    ]


# Generated with AI
def test_price_in_gives_the_same_number_as_convert(mixed_books):
    for book in Book.objects.annotate(eur=price_in("EUR")):
        assert book.eur == convert(book.price, book.currency_id, "EUR")


# Generated with AI
def test_price_in_filters_by_a_range_in_another_currency(mixed_books):
    books = Book.objects.annotate(usd=price_in("USD")).filter(usd__gte=12, usd__lte=20)

    assert sorted(book.title for book in books) == ["20 USD", "650 UAH"]


# Generated with AI
def test_a_book_in_a_currency_without_a_rate_has_no_converted_price():
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")
    BookFactory(currency_id="PLN")

    assert Book.objects.annotate(uah=price_in("UAH")).get().uah is None


# Generated with AI
def test_price_in_a_currency_without_a_rate_fails():
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")
    with pytest.raises(RateUnavailable, match="PLN"):
        price_in("PLN")


# Generated with AI
def test_price_in_works_across_a_relation(mixed_books):
    category = CategoryFactory()
    category.books.set(Book.objects.all())

    result = Category.objects.annotate(
        avg_uah=Avg(price_in("UAH", price="books__price", currency="books__currency"))
    ).get(pk=category.pk)

    # (650.00 + 908.55 + 503.38) / 3
    assert result.avg_uah.quantize(Decimal("0.01")) == Decimal("687.31")


# ---------------------------------------------------------------------------
# seed_books and book_stats
# ---------------------------------------------------------------------------


# Generated with AI
def test_seed_books_adds_a_few_books_in_other_currencies():
    call_command("seed_books", stdout=StringIO())

    assert dict(Book.objects.exclude(currency="UAH").values_list("title", "currency")) == {
        "Гра престолів": "EUR",
        "Таємне життя дерев": "USD",
        "Воно": "USD",
    }


# Generated with AI
def test_book_stats_compares_prices_in_hryvnias():
    call_command("seed_books", stdout=StringIO())
    out = StringIO()

    call_command("book_stats", "--max-price", "300", stdout=out)

    output = out.getvalue()
    # 4.50 USD = 204.42 UAH: cheaper than 300 UAH, so it is listed
    assert "4.50 USD = 204.42 UAH" in output
    # 11.00 USD = 499.70 UAH: in the search by author, not in "price <= 300"
    cheap = output.split("filter: in stock and price <= 300")[1].split("filter: low stock")[0]
    assert "Воно" not in cheap
