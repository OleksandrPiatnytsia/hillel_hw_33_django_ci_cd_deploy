"""The currency of a format's price (BookFormat.currency) and prices in one currency in SQL."""

from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.db.models import Avg
from django.db.models.deletion import ProtectedError
from django.urls import reverse

from books.forms import BookFormatForm
from books.models import Book, BookFormat, Category
from currencies.models import Currency, ExchangeRate
from currencies.services import RateUnavailable, convert, price_in

from ..factories import BookFactory, BookFormatFactory, CategoryFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 16)


@pytest.fixture(autouse=True)
def rates(monkeypatch):
    """16.11.2026: 1 USD = 45.4274 UAH, 1 EUR = 50.3379 UAH."""
    monkeypatch.setattr("currencies.services.today", lambda: TODAY)
    ExchangeRate.objects.create(currency_id="USD", date=TODAY, rate=Decimal("45.4274"))
    ExchangeRate.objects.create(currency_id="EUR", date=TODAY, rate=Decimal("50.3379"))


def form_data(**changes):
    """One format of the book form: the price and its currency live there."""
    data = {"format_type": "paper", "price": "20.00", "currency": "USD", "is_active": "on"}
    return {**data, **changes}


# ---------------------------------------------------------------------------
# The field
# ---------------------------------------------------------------------------


# Generated with AI
def test_a_new_format_is_in_hryvnias_by_default():
    assert BookFactory().formats.get().currency_id == "UAH"


# Generated with AI
def test_a_currency_with_formats_cannot_be_deleted():
    BookFactory(currency_id="USD")
    with pytest.raises(ProtectedError):
        Currency.objects.get(code="USD").delete()


# Generated with AI
def test_format_form_saves_the_currency():
    form = BookFormatForm(data=form_data(), instance=BookFormat(book=BookFactory(formats=False)))

    assert form.is_valid(), form.errors
    assert form.save().currency_id == "USD"


# Generated with AI
def test_format_form_offers_active_currencies_with_uah_preselected():
    Currency.objects.filter(code="EUR").update(is_active=False)

    form = BookFormatForm()

    choices = [label for _value, label in form.fields["currency"].choices]
    assert choices == ["UAH (₴)", "USD ($)"]  # no empty "------" choice
    assert form["currency"].value() == "UAH"


# Generated with AI
def test_format_form_keeps_the_turned_off_currency_of_the_format():
    book = BookFactory(currency_id="EUR")
    Currency.objects.filter(code="EUR").update(is_active=False)

    form = BookFormatForm(instance=book.formats.get())

    assert "EUR (€)" in [label for _value, label in form.fields["currency"].choices]


# Generated with AI
def test_format_form_refuses_a_turned_off_currency_for_another_format():
    Currency.objects.filter(code="EUR").update(is_active=False)

    form = BookFormatForm(data=form_data(currency="EUR"))

    assert "currency" in form.errors


# Generated with AI
def test_admin_book_list_shows_the_formats_and_the_price_from_in_hryvnias(admin_client):
    book = BookFactory(title="In dollars", price=Decimal("20.00"), currency_id="USD")
    BookFormatFactory(book=book, format_type="ebook", price=Decimal("5.00"), is_active=False)
    BookFactory(title="E-book", format_type="ebook")

    response = admin_client.get(
        reverse("admin:books_book_changelist") + "?formats__format_type=paper"
    )

    assert response.status_code == 200
    assert [book.title for book in response.context["cl"].result_list] == ["In dollars"]
    # Every format with its own price, the one not on sale struck through
    assert "Паперова&nbsp;20,00 $" in response.text
    assert "line-through" in response.text
    # The price "from": the paper book on sale, in UAH (20 * 45.4274)
    assert 'field-price_from">908,55 ₴</td>' in response.text
    # A book without a format on sale has no price "from"
    BookFactory(title="Not on sale", formats=False)
    response = admin_client.get(reverse("admin:books_book_changelist"), {"q": "Not on sale"})
    assert 'field-price_from">—</td>' in response.text


# ---------------------------------------------------------------------------
# price_in(): a price in one currency, calculated by the database
# ---------------------------------------------------------------------------


@pytest.fixture
def mixed_books():
    """Three books, each with one format in its own currency."""
    BookFactory(title="650 UAH", price=Decimal("650.00"))  # 14.31 USD
    BookFactory(title="20 USD", price=Decimal("20.00"), currency_id="USD")
    BookFactory(title="10 EUR", price=Decimal("10.00"), currency_id="EUR")  # 11.08 USD


# Generated with AI
def test_price_in_sorts_formats_of_different_currencies(mixed_books):
    formats = BookFormat.objects.annotate(usd=price_in("USD")).order_by("usd")

    assert [(f.book.title, f.usd) for f in formats] == [
        ("10 EUR", Decimal("11.08")),
        ("650 UAH", Decimal("14.31")),
        ("20 USD", Decimal("20.00")),
    ]


# Generated with AI
def test_price_in_gives_the_same_number_as_convert(mixed_books):
    for book_format in BookFormat.objects.annotate(eur=price_in("EUR")):
        assert book_format.eur == convert(book_format.price, book_format.currency_id, "EUR")


# Generated with AI
def test_price_in_filters_by_a_range_in_another_currency(mixed_books):
    formats = BookFormat.objects.annotate(usd=price_in("USD")).filter(usd__gte=12, usd__lte=20)

    assert sorted(f.book.title for f in formats) == ["20 USD", "650 UAH"]


# Generated with AI
def test_a_format_in_a_currency_without_a_rate_has_no_converted_price():
    Currency.objects.create(code="PLN", name="Zloty", symbol="zł")
    BookFactory(currency_id="PLN")

    assert BookFormat.objects.annotate(uah=price_in("UAH")).get().uah is None


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
        avg_uah=Avg(
            price_in("UAH", price="books__formats__price", currency="books__formats__currency")
        )
    ).get(pk=category.pk)

    # (650.00 + 908.55 + 503.38) / 3
    assert result.avg_uah.quantize(Decimal("0.01")) == Decimal("687.31")


# ---------------------------------------------------------------------------
# seed_books and book_stats
# ---------------------------------------------------------------------------


# Generated with AI
def test_seed_books_adds_a_few_formats_in_other_currencies():
    call_command("seed_books", stdout=StringIO())

    other = BookFormat.objects.exclude(currency="UAH").values_list(
        "book__title", "format_type", "currency"
    )
    assert sorted(other) == [
        ("Воно", "paper", "USD"),
        ("Гра престолів", "ebook", "USD"),
        ("Гра престолів", "paper", "EUR"),
        ("Таємне життя дерев", "audiobook", "USD"),
    ]


# Generated with AI
def test_book_stats_compares_prices_in_hryvnias():
    call_command("seed_books", stdout=StringIO())
    out = StringIO()

    call_command("book_stats", "--max-price", "300", stdout=out)

    output = out.getvalue()
    cheap = output.split("filter: in stock and price <= 300")[1].split("filter: low stock")[0]
    # The audiobook of 4.50 USD = 204.42 UAH: cheaper than 300 UAH, and a
    # file is always in stock
    assert "Таємне життя дерев" in cheap and "from 204.42 UAH" in cheap
    # 11.00 USD = 499.70 UAH: in the search by author, not in "price <= 300"
    assert "Воно" not in cheap
