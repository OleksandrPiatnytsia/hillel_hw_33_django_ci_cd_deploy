"""Formats of a book: paper, e-book, audiobook, each with its own price.

Stage 1 of the formats: the model BookFormat and its checks, the data
migration (one format for every existing book), the rights of the groups,
the admin inline, the cache of the book pages, seed_books.
"""

import importlib
import re
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.apps import apps
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse

from django.conf import settings
from django.test import RequestFactory

from books.cache import book_key, get_cached_book
from books.models import Book, BookFormat
from currencies.display import SESSION_KEY, price_from
from currencies.models import ExchangeRate

from ..factories import AuthorFactory, BookFactory, BookFormatFactory, UserFactory
from ..helpers import admin_change_form_data, format_row, formats_data

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 16)

PAPER = BookFormat.FormatType.PAPER
EBOOK = BookFormat.FormatType.EBOOK
AUDIOBOOK = BookFormat.FormatType.AUDIOBOOK

# The data migration: a module name that starts with a digit can't be
# imported with "import"
create_book_formats = importlib.import_module("books.migrations.0014_create_book_formats")


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------


# Generated with AI
def test_one_book_in_three_formats_with_own_prices():
    book = BookFactory(formats=False)
    BookFormatFactory(book=book, format_type=AUDIOBOOK, price="249.00")
    BookFormatFactory(book=book, format_type=PAPER, price="450.00")
    BookFormatFactory(book=book, format_type=EBOOK, price="199.00", currency_id="USD")

    formats = list(book.formats.all())

    # Paper, e-book, audiobook: Meta.ordering, not the alphabet of the values
    assert [f.format_type for f in formats] == [PAPER, EBOOK, AUDIOBOOK]
    assert [f.price for f in formats] == [Decimal("450.00"), Decimal("199.00"), Decimal("249.00")]
    assert formats[1].currency_id == "USD"
    # Defaults: in UAH and on sale
    assert formats[0].currency_id == "UAH"
    assert all(f.is_active for f in formats)


# Generated with AI
def test_a_book_has_only_one_format_of_a_type():
    book = BookFactory()  # with its paper format

    # The check of the forms (validate_constraints in full_clean)
    with pytest.raises(ValidationError) as error:
        BookFormat(book=book, format_type=PAPER, price=1).full_clean()
    assert "__all__" in error.value.message_dict

    # The database itself
    with pytest.raises(IntegrityError), transaction.atomic():
        BookFormat.objects.create(book=book, format_type=PAPER, price=1)


# Generated with AI
@pytest.mark.parametrize("format_type", [EBOOK, AUDIOBOOK])
def test_only_the_paper_format_has_a_cover_type(format_type):
    book_format = BookFormatFactory.build(
        book=BookFactory(), format_type=format_type, cover_type=BookFormat.CoverType.HARD
    )

    with pytest.raises(ValidationError) as error:
        book_format.full_clean()

    assert "cover_type" in error.value.message_dict


# Generated with AI
def test_an_audiobook_has_no_pages_but_an_ebook_has():
    book = BookFactory()
    audiobook = BookFormatFactory.build(book=book, format_type=AUDIOBOOK, pages=300)
    ebook = BookFormatFactory.build(book=book, format_type=EBOOK, pages=300)

    with pytest.raises(ValidationError) as error:
        audiobook.full_clean()
    assert "pages" in error.value.message_dict
    ebook.full_clean()  # no error


# Generated with AI
def test_a_negative_price_is_refused():
    book_format = BookFormatFactory.build(book=BookFactory(), price="-1.00")

    with pytest.raises(ValidationError) as error:
        book_format.full_clean()

    assert "price" in error.value.message_dict


# Generated with AI
def test_formats_are_deleted_with_their_book():
    book_format = BookFormatFactory()

    book_format.book.delete()

    assert not BookFormat.objects.filter(pk=book_format.pk).exists()


# Generated with AI
def test_str_is_the_title_and_the_format():
    book_format = BookFormatFactory(book=BookFactory(title="Тигролови"), format_type=EBOOK)

    assert str(book_format) == f"Тигролови — {book_format.get_format_type_display()}"


# ---------------------------------------------------------------------------
# Data migration books.0014: one format for every existing book (the
# copies of the old book fields: tests/integration/test_format_migrations.py)
# ---------------------------------------------------------------------------


# Generated with AI
def test_migration_skips_books_that_already_have_a_format():
    book = BookFactory(price="100.00", formats=False)
    BookFormatFactory(book=book, format_type=EBOOK, price="50.00")

    create_book_formats.create_formats(apps, None)

    assert list(book.formats.values_list("format_type", "price")) == [(EBOOK, Decimal("50.00"))]


# Generated with AI
def test_migration_reverse_deletes_the_formats():
    BookFormatFactory()

    create_book_formats.delete_formats(apps, None)

    assert not BookFormat.objects.exists()


# ---------------------------------------------------------------------------
# Rights of the groups (users.0007)
# ---------------------------------------------------------------------------


ALL_FORMAT_RIGHTS = {"view_bookformat", "add_bookformat", "change_bookformat", "delete_bookformat"}


# Generated with AI
@pytest.mark.parametrize(
    "group, expected",
    [
        ("Customers", {"view_bookformat"}),
        ("Editors", ALL_FORMAT_RIGHTS),
        ("Managers", ALL_FORMAT_RIGHTS),
    ],
)
def test_groups_get_the_format_rights_like_the_book_category_rights(group, expected):
    codenames = set(
        Group.objects.get(name=group)
        .permissions.filter(codename__endswith="_bookformat")
        .values_list("codename", flat=True)
    )

    assert codenames == expected


# ---------------------------------------------------------------------------
# Admin: the formats inline on the book page
# ---------------------------------------------------------------------------


def _change_url(book):
    return reverse("admin:books_book_change", args=[book.pk])


def _admin_book_data(page):
    """The book form as the browser sends it, without a new cover file.

    admin_change_form_data() copies the initial value of "cover": an empty
    ImageFieldFile, which can't be sent as a file.
    """
    data = admin_change_form_data(page)
    data["cover"] = ""
    return data


# Generated with AI
def test_admin_add_book_page_has_one_empty_format_row(superuser_client):
    response = superuser_client.get(reverse("admin:books_book_add"))

    content = response.content.decode()
    assert 'name="formats-TOTAL_FORMS" value="1"' in content
    assert 'name="formats-0-format_type"' in content


# Generated with AI
def test_admin_adds_a_format_to_a_book(superuser_client):
    book = BookFactory()  # with its paper format, 250.00
    page = superuser_client.get(_change_url(book))
    data = _admin_book_data(page)
    data.update(
        {
            "formats-TOTAL_FORMS": 2,
            "formats-1-format_type": EBOOK,
            "formats-1-price": "199.00",
            "formats-1-currency": "UAH",
            "formats-1-is_active": "on",
        }
    )

    response = superuser_client.post(_change_url(book), data)

    assert response.status_code == 302, response.context and response.context["errors"]
    assert list(book.formats.values_list("format_type", "price")) == [
        (PAPER, Decimal("250.00")),
        (EBOOK, Decimal("199.00")),
    ]


# Generated with AI
def test_admin_refuses_a_cover_for_an_ebook(superuser_client):
    book = BookFactory(formats=False)
    page = superuser_client.get(_change_url(book))
    data = _admin_book_data(page)
    data.update(
        {
            "formats-TOTAL_FORMS": 1,
            "formats-0-format_type": EBOOK,
            "formats-0-price": "199.00",
            "formats-0-currency": "UAH",
            "formats-0-cover_type": "hard",
        }
    )

    response = superuser_client.post(_change_url(book), data)

    assert response.status_code == 200  # the form again, with the error
    assert not book.formats.exists()


# Generated with AI
def test_editor_sees_the_formats_inline(client):
    editor = UserFactory(groups=["Editors"], is_staff=True)
    client.force_login(editor)
    book = BookFactory()  # with its paper format

    response = client.get(_change_url(book))

    assert response.status_code == 200
    assert 'name="formats-TOTAL_FORMS"' in response.content.decode()


# ---------------------------------------------------------------------------
# Cache of the book pages
# ---------------------------------------------------------------------------


# Generated with AI
@pytest.mark.parametrize("change", ["save", "delete"])
def test_a_changed_format_drops_the_cache_of_its_book(change):
    book_format = BookFormatFactory()
    other = BookFactory()
    get_cached_book(book_format.book_id)
    get_cached_book(other.pk)

    if change == "save":
        book_format.price = Decimal("1.00")
        book_format.save()
    else:
        book_format.delete()

    assert cache.get(book_key(book_format.book_id)) is None
    assert cache.get(book_key(other.pk)) is not None


# ---------------------------------------------------------------------------
# seed_books
# ---------------------------------------------------------------------------


# Generated with AI
def test_seed_books_gives_every_demo_book_its_formats():
    call_command("seed_books", stdout=StringIO())

    assert not Book.objects.filter(formats__isnull=True).exists()
    hobbit = Book.objects.get(title="Хоббіт")
    assert [(f.format_type, f.price, f.cover_type, f.pages) for f in hobbit.formats.all()] == [
        (PAPER, Decimal("99.75"), "hard", 304),
        (EBOOK, Decimal("79.00"), "", 304),
        (AUDIOBOOK, Decimal("149.00"), "", None),
    ]
    assert hobbit.stock == 3437  # the copies of the paper book
    # Every format passes the checks of the form
    for book_format in BookFormat.objects.all():
        book_format.full_clean()
    # All three types for the filters of the catalog
    assert set(BookFormat.objects.values_list("format_type", flat=True)) == {
        PAPER,
        EBOOK,
        AUDIOBOOK,
    }
    # A book only as an e-book: no copies, always available
    witcher = Book.objects.with_availability().get(title="Відьмак. Останнє бажання")
    assert (witcher.stock, witcher.available) == (0, True)


# Generated with AI
def test_seed_books_keeps_the_formats_a_book_already_has():
    call_command("seed_books", stdout=StringIO())
    # A manager changes a price and deletes a format
    book = Book.objects.get(title="Хоббіт")
    book.formats.filter(format_type=PAPER).update(price=Decimal("1.00"))
    book.formats.filter(format_type=AUDIOBOOK).delete()
    out = StringIO()

    call_command("seed_books", stdout=out)

    assert list(book.formats.values_list("format_type", "price")) == [
        (PAPER, Decimal("1.00")),
        (EBOOK, Decimal("79.00")),
    ]
    assert "+ formats of" not in out.getvalue()


# ===========================================================================
# Stage 2: the catalog and the book page
# ===========================================================================


@pytest.fixture
def rates(monkeypatch):
    """USD and EUR rates of the NBU: the formats can be in other currencies."""
    monkeypatch.setattr("currencies.services.today", lambda: TODAY)
    ExchangeRate.objects.create(currency_id="USD", date=TODAY, rate=Decimal("40.0000"))
    ExchangeRate.objects.create(currency_id="EUR", date=TODAY, rate=Decimal("50.0000"))


def _book_with_formats(title="Тигролови", paper="450.00", ebook="199.00", audiobook=None, **book):
    """A book in its paper format (from the factory) + an e-book (+ an audiobook)."""
    book = BookFactory(title=title, price=paper, **book)
    if ebook:
        BookFormatFactory(book=book, format_type=EBOOK, price=ebook)
    if audiobook:
        BookFormatFactory(book=book, format_type=AUDIOBOOK, price=audiobook)
    return book


def _request(currency=None):
    request = RequestFactory().get("/")
    request.session = {SESSION_KEY: currency} if currency else {}
    return request


# ---------------------------------------------------------------------------
# The price "from": Book.objects.with_display_price() and price_from()
# ---------------------------------------------------------------------------


# Generated with AI
def test_display_price_is_the_cheapest_format_on_sale(rates):
    book = _book_with_formats(paper="450.00", ebook="5.00")  # 5 USD = 200 UAH
    book.formats.filter(format_type=EBOOK).update(currency_id="USD")
    BookFormatFactory(book=book, format_type=AUDIOBOOK, price="100.00", is_active=False)

    found = Book.objects.with_display_price("UAH").get(pk=book.pk)

    # The audiobook is cheaper, but not on sale; the e-book in dollars wins
    assert found.display_price == Decimal("200.00")
    assert Book.objects.with_display_price("USD").get(pk=book.pk).display_price == Decimal("5.00")


# Generated with AI
def test_display_price_of_a_book_without_formats_on_sale_is_none():
    book = BookFactory(formats=False)
    off = BookFactory()
    off.formats.update(is_active=False)

    prices = dict(Book.objects.with_display_price("UAH").values_list("pk", "display_price"))

    assert prices == {book.pk: None, off.pk: None}


# Generated with AI
def test_price_from_picks_the_cheapest_format_in_the_switchers_currency(rates):
    book = _book_with_formats(paper="450.00", ebook="5.00")
    book.formats.filter(format_type=EBOOK).update(currency_id="USD")
    book.refresh_from_db()

    in_uah = price_from(_request(), book)
    in_usd = price_from(_request("USD"), book)

    assert (in_uah.amount, in_uah.currency.code) == (Decimal("200.00"), "UAH")
    assert in_uah.converted and in_uah.original_amount == Decimal("5.00")
    assert (in_usd.amount, in_usd.converted) == (Decimal("5.00"), False)


# Generated with AI
def test_price_from_is_none_without_formats_on_sale():
    assert price_from(_request(), BookFactory(formats=False)) is None


# Generated with AI
def test_active_formats_come_from_one_query_for_the_whole_list(django_assert_num_queries):
    for number in range(3):
        _book_with_formats(title=f"Book {number}")

    with django_assert_num_queries(2):  # the books + their formats
        books = list(Book.objects.with_active_formats())
        formats = [[f.format_type for f in book.active_formats] for book in books]

    assert formats == [[PAPER, EBOOK]] * 3


# Generated with AI
def test_active_formats_without_prefetch_and_of_an_unsaved_book(django_assert_num_queries):
    book = _book_with_formats(audiobook="249.00")
    book.formats.filter(format_type=EBOOK).update(is_active=False)
    book = Book.objects.get(pk=book.pk)

    with django_assert_num_queries(1):  # read once, then kept
        assert [f.format_type for f in book.active_formats] == [PAPER, AUDIOBOOK]
        assert book.paper_format.format_type == PAPER
        assert book.format_of_type(EBOOK) is None
    with django_assert_num_queries(0):
        assert Book(title="Draft").active_formats == []


# Generated with AI
def test_pages_count_is_of_the_paper_format_else_of_the_ebook():
    book = BookFactory(pages=320)
    BookFormatFactory(book=book, format_type=EBOOK, price="1.00", pages=300)
    ebook_only = BookFactory(format_type=BookFormat.FormatType.EBOOK, pages=280)
    unknown = BookFactory()

    assert (book.pages_count, ebook_only.pages_count, unknown.pages_count) == (320, 280, None)


# ---------------------------------------------------------------------------
# The catalog: the card, the price filter and sort, the format filters
# ---------------------------------------------------------------------------


def _catalog(client, params=None, language="uk"):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    return client.get(reverse("books:list"), params or {})


def _titles(response):
    return [book.title for book in response.context["books"]]


# Generated with AI
def test_card_of_a_book_in_several_formats_says_from_and_leads_to_the_book(client):
    book = _book_with_formats(paper="450.00", ebook="199.00")

    content = _catalog(client).content.decode()

    assert "від 199,00 ₴" in content
    assert "Обрати формат" in content
    assert f'href="{book.get_absolute_url()}">Обрати формат' in content
    # No "Add to cart" form for this card
    assert reverse("cart:add", args=[book.pk]) not in content


# Generated with AI
def test_card_of_a_book_in_one_format_adds_that_format_to_the_cart(client):
    book = BookFactory(price="250.00")

    content = _catalog(client).content.decode()

    assert "250,00 ₴" in content and "від 250" not in content
    assert reverse("cart:add", args=[book.pk]) in content
    assert f'name="format" value="{book.formats.get().pk}"' in content


# Generated with AI
def test_card_of_a_book_not_on_sale(client):
    BookFactory(formats=False)

    content = _catalog(client).content.decode()

    assert "Немає в продажу" in content
    assert 'type="submit" disabled' in content


# Generated with AI
def test_catalog_sorts_and_filters_by_the_price_from(client):
    _book_with_formats(title="Cheap e-book", paper="900.00", ebook="100.00")
    BookFactory(title="Paper only", price="300.00")

    by_price = _catalog(client, {"sort": "price"})
    cheap = _catalog(client, {"price_max": "150"})

    assert _titles(by_price) == ["Cheap e-book", "Paper only"]
    # 900 for paper, but "from 100": in the range
    assert _titles(cheap) == ["Cheap e-book"]
    # The slider: from the cheapest "from" to the dearest "from"
    assert by_price.context["price_range"] == {"min": 100, "max": 300}


# Generated with AI
def test_catalog_book_type_filter_looks_at_the_formats_on_sale(client):
    _book_with_formats(title="Paper and e-book")
    BookFactory(title="Paper only")
    turned_off = _book_with_formats(title="E-book turned off")
    turned_off.formats.filter(format_type=EBOOK).update(is_active=False)

    assert _titles(_catalog(client, {"book_type": "ebook"})) == ["Paper and e-book"]
    assert _titles(_catalog(client, {"book_type": ["ebook", "paper"]})) == [
        "E-book turned off",
        "Paper and e-book",
        "Paper only",
    ]


# Generated with AI
def test_catalog_cover_filter_looks_at_the_paper_format(client):
    BookFactory(title="Hard paper", cover_type="hard")
    BookFactory(title="Soft paper", cover_type="soft")

    response = _catalog(client, {"cover_type": "hard"})

    assert _titles(response) == ["Hard paper"]
    form = response.context["filter_form"]
    assert [value for value, _label in form.fields["cover_type"].choices] == ["hard", "soft"]


# Generated with AI
def test_catalog_panel_offers_only_the_formats_on_sale(client):
    book = _book_with_formats(audiobook="249.00")
    book.formats.filter(format_type=AUDIOBOOK).update(is_active=False)

    form = _catalog(client).context["filter_form"]

    assert [value for value, _label in form.fields["book_type"].choices] == [PAPER, EBOOK]


# Generated with AI
def test_catalog_needs_no_query_per_card_for_the_formats(client):
    for number in range(3):
        _book_with_formats(title=f"Book {number}")
    _catalog(client)  # the caches of the page are warm now
    queries_for_3 = len(_queries_of(client))

    for number in range(3, 9):
        _book_with_formats(title=f"Book {number}")

    assert len(_queries_of(client)) == queries_for_3


def _queries_of(client):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        _catalog(client)
    return queries.captured_queries


# ---------------------------------------------------------------------------
# The book page: the format tiles and the details
# ---------------------------------------------------------------------------


def _page(client, book, language="uk"):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    return client.get(reverse("books:detail", args=[book.pk])).content.decode()


# Generated with AI
def test_book_page_has_a_tile_per_format_on_sale_with_its_price(client):
    book = _book_with_formats(paper="450.00", ebook="199.00", audiobook="249.00")
    book.formats.filter(format_type=AUDIOBOOK).update(is_active=False)
    paper, ebook = book.formats.filter(is_active=True)

    content = _page(client, book)

    assert content.count('class="btn-check"') == 2
    assert f'value="{paper.pk}"' in content and f'value="{ebook.pk}"' in content
    # Paper is chosen; the labels and the prices of the tiles
    # The paper tile is the only chosen one: "checked" stands right after its id
    assert content.count("checked") == 1
    assert re.search(rf'id="format-{paper.pk}" autocomplete="off"\s+checked', content)
    for text in ["Паперова", "450,00 ₴", "Електронна", "199,00 ₴"]:
        assert text in content, text
    # No price "from" above the tiles: every tile has its own price
    assert "від 199,00 ₴" not in content
    assert "Аудіокнига" not in content.split("format-tiles")[1].split("</fieldset>")[0]


# Generated with AI
def test_book_page_of_one_format_has_one_tile(client):
    # One format looks the same as several: a chosen tile with its price
    book = BookFactory(price="250.00")
    paper = book.formats.get()

    content = _page(client, book)

    assert content.count('class="btn-check"') == 1
    assert re.search(rf'id="format-{paper.pk}" autocomplete="off"\s+checked', content)
    tiles = content.split("format-tiles")[1].split("</fieldset>")[0]
    assert "Паперова" in tiles and "250,00 ₴" in tiles
    assert "від 250" not in content


# Generated with AI
def test_book_page_of_a_book_not_on_sale(client):
    book = BookFactory(formats=False)

    content = _page(client, book)

    assert "Немає в продажу" in content
    assert reverse("cart:add", args=[book.pk]) not in content


# Generated with AI
def test_book_page_shows_a_new_format_at_once(client):
    book = BookFactory(price="250.00")
    assert "Електронна" not in _page(client, book)  # cached now

    BookFormatFactory(book=book, format_type=EBOOK, price="99.00")

    content = _page(client, book)
    assert "Електронна" in content and "99,00 ₴" in content


# Generated with AI
def test_book_page_details_list_the_formats_and_the_paper_cover(client):
    book = _book_with_formats(cover_type="hard", pages=320)

    content = _page(client, book, "en")

    details = content.split("book-details")[1].split("</dl>")[0]
    for text in ["Formats", "Paper, E-book", "Hardcover", "320"]:
        assert text in details, text


# Generated with AI
def test_search_suggestions_show_the_price_from(client):
    _book_with_formats(title="Тигролови", paper="450.00", ebook="199.00")
    BookFactory(title="Тигролов-2", price="300.00")
    BookFactory(title="Тигр без формату", formats=False)

    response = client.get(reverse("books:search"), {"q": "Тигр"})

    prices = {book["title"]: book["price"] for book in response.json()["results"]}
    assert prices == {
        "Тигр без формату": "",
        "Тигролов-2": "300,00 ₴",
        "Тигролови": "від 199,00 ₴",
    }


# Generated with AI
def test_author_page_shows_the_price_from(client):
    book = _book_with_formats(paper="450.00", ebook="199.00")

    response = client.get(reverse("books:author_detail", args=[book.author.pk]))

    assert "від 199,00 ₴" in response.content.decode()


# ---------------------------------------------------------------------------
# The book form of the site: the formats block
# ---------------------------------------------------------------------------


# Generated with AI
def test_book_form_page_has_three_format_rows_for_a_new_book(manager_client):
    response = manager_client.get(reverse("books:create"))

    formats = response.context["formats"]
    assert len(formats.forms) == 3
    content = response.content.decode()
    assert 'name="formats-TOTAL_FORMS" value="3"' in content
    # Nothing to remove yet
    assert 'name="formats-0-DELETE"' not in content


# Generated with AI
def test_book_form_page_of_a_book_shows_its_formats_and_free_rows(manager_client):
    book = _book_with_formats()

    response = manager_client.get(reverse("books:update", args=[book.pk]))

    formats = response.context["formats"]
    assert [form.instance.format_type for form in formats.forms[:2]] == [PAPER, EBOOK]
    assert len(formats.forms) == 3  # max three formats
    assert 'name="formats-0-DELETE"' in response.content.decode()


# Generated with AI
def test_editor_creates_a_book_in_two_formats(client):
    client.force_login(UserFactory(groups=["Editors"]))
    author = AuthorFactory()

    response = client.post(
        reverse("books:create"),
        {
            "title": "Тигролови",
            "author": author.pk,
            "description": "",
            **formats_data(
                format_row(price="450.00", cover_type="hard", pages="320"),
                format_row(EBOOK, price="5.00", currency="USD"),
            ),
        },
    )

    book = Book.objects.get(title="Тигролови")
    assert response.status_code == 302
    paper, ebook = book.formats.all()
    assert (paper.cover_type, paper.pages, ebook.currency_id) == ("hard", 320, "USD")


# Generated with AI
def test_book_form_shows_the_error_of_a_format_row(manager_client):
    response = manager_client.post(
        reverse("books:create"),
        {
            "title": "Тигролови",
            "author": AuthorFactory().pk,
            "description": "",
            **formats_data(format_row(AUDIOBOOK, pages="300")),
        },
    )

    assert response.status_code == 200
    assert "В аудіокниги немає сторінок." in response.content.decode()
    assert not Book.objects.exists()
