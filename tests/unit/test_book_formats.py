"""Formats of a book: paper, e-book, audiobook, each with its own price.

Stage 1 of the formats: the model BookFormat and its checks, the data
migration (one format for every existing book), the rights of the groups,
the admin inline, the cache of the book pages, seed_books.
"""

import importlib
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

from books.cache import book_key, get_cached_book
from books.models import Book, BookFormat

from ..factories import BookFactory, BookFormatFactory, UserFactory
from ..helpers import admin_change_form_data

pytestmark = pytest.mark.django_db

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
    book = BookFactory()
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
    book = BookFactory()
    BookFormatFactory(book=book, format_type=PAPER)

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
        book=BookFactory(), format_type=format_type, cover_type=Book.CoverType.HARD
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
# Data migration books.0014: one format for every existing book
# ---------------------------------------------------------------------------


# Generated with AI
def test_migration_makes_a_format_from_the_fields_of_the_book():
    paper = BookFactory(price="450.00", currency_id="EUR", cover_type="hard", pages=320)
    audiobook = BookFactory(price="249.00", book_type=Book.BookType.AUDIOBOOK, pages=10)

    create_book_formats.create_formats(apps, None)

    paper_format = paper.formats.get()
    assert (paper_format.format_type, paper_format.price, paper_format.currency_id) == (
        PAPER,
        Decimal("450.00"),
        "EUR",
    )
    assert (paper_format.cover_type, paper_format.pages) == ("hard", 320)
    # An audiobook keeps its price, but no pages (BookFormat.clean())
    audiobook_format = audiobook.formats.get()
    assert audiobook_format.format_type == AUDIOBOOK
    assert audiobook_format.pages is None
    audiobook_format.full_clean()


# Generated with AI
def test_migration_drops_a_cover_of_a_non_paper_book():
    # Saved past the form (Book.clean() is not called by save())
    ebook = BookFactory(book_type=Book.BookType.EBOOK, cover_type="soft")

    create_book_formats.create_formats(apps, None)

    assert ebook.formats.get().cover_type == ""


# Generated with AI
def test_migration_skips_books_that_already_have_a_format():
    book = BookFactory(price="100.00")
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
    book = BookFactory()
    BookFormatFactory(book=book, format_type=PAPER)
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
    book = BookFactory()
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
    book = BookFactory()
    BookFormatFactory(book=book)

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
def test_seed_books_gives_every_demo_book_a_format():
    call_command("seed_books", stdout=StringIO())

    assert not Book.objects.filter(formats__isnull=True).exists()
    # The format has the price and currency of the book
    book = Book.objects.exclude(currency_id="UAH").first()
    book_format = book.formats.get()
    assert (book_format.price, book_format.currency_id) == (book.price, book.currency_id)


# Generated with AI
def test_seed_books_keeps_the_formats_a_book_already_has():
    call_command("seed_books", stdout=StringIO())
    book = Book.objects.first()
    book.formats.update(price=Decimal("1.00"))
    out = StringIO()

    call_command("seed_books", stdout=out)

    assert book.formats.get().price == Decimal("1.00")
    assert "+ format of" not in out.getvalue()
