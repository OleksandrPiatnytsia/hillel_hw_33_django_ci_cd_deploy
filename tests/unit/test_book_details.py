"""The details of the edition: publisher, type, cover, language, year, pages.

Stage 1 of the new Book fields: the model and its checks, the data
migrations (the publishers, the rights of the groups), the admin and the
cache of the book pages.
"""

import pytest
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.urls import reverse
from django.utils import timezone, translation

from books.cache import book_key, get_cached_book
from books.models import Book, Publisher

from ..factories import BookFactory

pytestmark = pytest.mark.django_db


# Generated with AI
def test_a_book_without_details_is_valid_and_a_paper_book():
    book = BookFactory()

    book.full_clean()

    assert book.book_type == Book.BookType.PAPER
    assert book.publisher is None
    assert book.cover_type == ""
    assert book.language == ""
    assert book.publication_year is None
    assert book.pages is None


# Generated with AI
def test_all_details_are_saved_and_shown_with_their_labels():
    publisher = Publisher.objects.get(name="Видавництво Старого Лева")
    book = BookFactory(
        publisher=publisher,
        book_type=Book.BookType.PAPER,
        cover_type=Book.CoverType.DUST_JACKET,
        language=Book.Language.UKRAINIAN,
        publication_year=2020,
        pages=352,
    )

    book.full_clean()
    book.refresh_from_db()

    assert book.publisher == publisher
    with translation.override("en"):
        assert book.get_cover_type_display() == "Dust jacket"
        assert book.get_language_display() == "Ukrainian"
    assert (book.publication_year, book.pages) == (2020, 352)


# Generated with AI
@pytest.mark.parametrize("book_type", [Book.BookType.EBOOK, Book.BookType.AUDIOBOOK])
def test_only_a_paper_book_has_a_cover_type(book_type):
    book = BookFactory.build(book_type=book_type, cover_type=Book.CoverType.HARD)

    with pytest.raises(ValidationError) as error:
        book.clean()

    assert "cover_type" in error.value.message_dict


# Generated with AI
def test_an_ebook_without_a_cover_type_is_valid():
    BookFactory(book_type=Book.BookType.EBOOK).full_clean()


# Generated with AI
@pytest.mark.parametrize(
    "year, valid",
    [
        (1449, False),  # before the first printed books
        (1450, True),
        (2000, True),
        ("this year", True),
        ("next year", False),  # not published yet
    ],
)
def test_publication_year_limits(year, valid):
    this_year = timezone.now().year
    year = {"this year": this_year, "next year": this_year + 1}.get(year, year)
    book = BookFactory(publication_year=year)

    if valid:
        book.full_clean()
    else:
        with pytest.raises(ValidationError) as error:
            book.full_clean()
        assert "publication_year" in error.value.message_dict


# Generated with AI
@pytest.mark.parametrize("pages, valid", [(0, False), (1, True), (10000, True), (10001, False)])
def test_pages_limits(pages, valid):
    book = BookFactory(pages=pages)

    if valid:
        book.full_clean()
    else:
        with pytest.raises(ValidationError):
            book.full_clean()


# Generated with AI
def test_a_publisher_with_books_cannot_be_deleted():
    publisher = Publisher.objects.create(name="Test publisher")
    BookFactory(publisher=publisher)

    with pytest.raises(ProtectedError):
        publisher.delete()


# Generated with AI
def test_publishers_are_ordered_by_name_and_shown_by_name():
    names = list(Publisher.objects.values_list("name", flat=True))

    # The database sorts by its collation: the Ukrainian names first, the
    # Latin ones after them (Python's sorted() would put Latin first)
    assert names[0] == "А-БА-БА-ГА-ЛА-МА-ГА"
    assert names.index("Ранок") < names.index("Vivat")
    assert str(Publisher.objects.get(name="Ранок")) == "Ранок"


# ---------------------------------------------------------------------------
# Data migrations
# ---------------------------------------------------------------------------


# Generated with AI
def test_the_main_ukrainian_publishers_come_from_the_migration():
    names = set(Publisher.objects.values_list("name", flat=True))

    assert {
        "А-БА-БА-ГА-ЛА-МА-ГА",
        "Видавництво Старого Лева",
        "Наш Формат",
        "Ранок",
        "Vivat",
    } <= names
    assert len(names) >= 30


# Generated with AI
@pytest.mark.parametrize(
    "group, expected",
    [
        ("Customers", {"view_publisher"}),
        ("Editors", {"view_publisher", "add_publisher", "change_publisher"}),
        (
            "Managers",
            {"view_publisher", "add_publisher", "change_publisher", "delete_publisher"},
        ),
    ],
)
def test_groups_get_the_publisher_rights_like_the_author_rights(group, expected):
    codenames = set(
        Group.objects.get(name=group)
        .permissions.filter(codename__endswith="_publisher")
        .values_list("codename", flat=True)
    )

    assert codenames == expected


# Generated with AI
def test_groups_keep_their_older_rights():
    editors = Group.objects.get(name="Editors")

    # From users/0003: add(), not set(), in the new migration
    assert editors.permissions.filter(codename="change_author").exists()


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


# Generated with AI
def test_admin_book_page_has_the_details(superuser_client):
    book = BookFactory()

    response = superuser_client.get(reverse("admin:books_book_change", args=[book.pk]))

    content = response.content.decode()
    for field in ["publisher", "book_type", "cover_type", "language", "publication_year", "pages"]:
        assert f'name="{field}"' in content, field


# Generated with AI
def test_admin_publisher_list_counts_books(superuser_client):
    publisher = Publisher.objects.get(name="Ранок")
    BookFactory(publisher=publisher)
    BookFactory(publisher=publisher)

    response = superuser_client.get(reverse("admin:books_publisher_changelist"), {"q": "Ранок"})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [publisher]
    assert response.context["cl"].result_list[0].books_count == 2


# Generated with AI
def test_admin_book_list_filters_by_language(superuser_client):
    ukrainian = BookFactory(language=Book.Language.UKRAINIAN)
    BookFactory(language=Book.Language.ENGLISH)

    response = superuser_client.get(reverse("admin:books_book_changelist"), {"language": "uk"})

    assert list(response.context["cl"].result_list) == [ukrainian]


# Generated with AI
def test_admin_publisher_autocomplete_finds_by_name(superuser_client):
    response = superuser_client.get(
        reverse("admin:autocomplete"),
        {
            "app_label": "books",
            "model_name": "book",
            "field_name": "publisher",
            "term": "Старого",
        },
    )

    names = [item["text"] for item in response.json()["results"]]
    assert names == ["Видавництво Старого Лева"]


# ---------------------------------------------------------------------------
# Cache of the book pages
# ---------------------------------------------------------------------------


# Generated with AI
def test_a_renamed_publisher_drops_the_cache_of_its_books():
    publisher = Publisher.objects.create(name="Old name")
    book = BookFactory(publisher=publisher)
    other = BookFactory()
    get_cached_book(book.pk)
    get_cached_book(other.pk)

    publisher.name = "New name"
    publisher.save()

    assert cache.get(book_key(book.pk)) is None
    # Books of other publishers keep their cache
    assert cache.get(book_key(other.pk)) is not None
