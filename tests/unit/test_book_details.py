"""The details of the edition: publisher, type, cover, language, year, pages.

Stage 1 of the new Book fields: the model and its checks, the data
migrations (the publishers, the rights of the groups), the admin and the
cache of the book pages.
Stage 2: the book form of the site, the "Details" block of the book page,
seed_books.
"""

from io import StringIO

import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db.models import ProtectedError
from django.urls import reverse
from django.utils import timezone, translation

from books.cache import book_key, get_cached_book
from books.forms import BookForm
from books.models import Book, Publisher

from ..factories import AuthorFactory, BookFactory

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


# ---------------------------------------------------------------------------
# The book form of the site
# ---------------------------------------------------------------------------


def _form_data(**changes):
    data = {
        "title": "Kobzar",
        "author": AuthorFactory().pk,
        "price": "250.00",
        "currency": "UAH",
        "description": "",
        "book_type": "paper",
    }
    return {**data, **changes}


# Generated with AI
def test_book_form_saves_the_details():
    publisher = Publisher.objects.get(name="Ранок")
    form = BookForm(
        data=_form_data(
            publisher=publisher.pk,
            cover_type="soft",
            language="pl",
            publication_year="2015",
            pages="120",
        )
    )

    assert form.is_valid(), form.errors
    book = form.save()

    assert (book.publisher, book.cover_type, book.language) == (publisher, "soft", "pl")
    assert (book.publication_year, book.pages) == (2015, 120)


# Generated with AI
def test_book_form_details_are_optional_except_the_type():
    form = BookForm(data=_form_data(book_type=""))

    assert list(form.errors) == ["book_type"]


# Generated with AI
def test_book_form_shows_the_cover_error_of_an_ebook_under_the_cover_field():
    form = BookForm(data=_form_data(book_type="ebook", cover_type="hard"))

    assert list(form.errors) == ["cover_type"]


# Generated with AI
def test_book_form_rejects_a_future_year():
    form = BookForm(data=_form_data(publication_year=str(timezone.now().year + 1)))

    assert list(form.errors) == ["publication_year"]


# Generated with AI
def test_book_form_groups_the_details_and_keeps_the_cover_last():
    form = BookForm()

    assert [field.name for field in form.detail_fields()] == BookForm.DETAIL_FIELDS
    main = [field.name for field in form.main_fields()]
    assert "cover" not in main and "publisher" not in main
    # Empty choices say "not known", the year's arrows stop at this year
    with translation.override("en"):
        assert form.fields["language"].choices[0] == ("", "— Not known —")
        assert form.fields["publisher"].empty_label == "— Not known —"
    assert form.fields["publication_year"].widget.attrs["max"] == timezone.now().year


# Generated with AI
def test_book_form_page_has_the_details_block(manager_client):
    response = manager_client.get(reverse("books:create"))

    content = response.content.decode()
    assert "<fieldset" in content
    for field in BookForm.DETAIL_FIELDS:
        assert f'name="{field}"' in content, field
    # The cover after the details
    assert content.index('name="pages"') < content.index('name="cover"')


# ---------------------------------------------------------------------------
# The book page
# ---------------------------------------------------------------------------


def _page(client, book, language="uk"):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    return client.get(reverse("books:detail", args=[book.pk])).content.decode()


# Generated with AI
def test_book_page_shows_the_details_in_the_language_of_the_site(client):
    book = BookFactory(
        publisher=Publisher.objects.get(name="Фоліо"),
        cover_type="hard",
        language="en",
        publication_year=2017,
        pages=224,
    )

    content = _page(client, book, "uk")
    for text in ["Фоліо", "Тверда", "Англійська", "2017", "224"]:
        assert text in content, text

    # Another cached fragment for English: the labels are English
    content = _page(client, book, "en")
    for text in ["Details", "Hardcover", "English", "Paper book"]:
        assert text in content, text


# Generated with AI
def test_book_page_hides_unknown_details(client):
    book = BookFactory()

    content = _page(client, book, "en")

    # Only the type: the other details are not known
    assert "Paper book" in content
    for text in ["Publisher", "Publication year", "Pages"]:
        assert f'<dt class="col-sm-4 col-lg-3">{text}</dt>' not in content, text


# Generated with AI
def test_a_renamed_publisher_is_shown_on_the_book_page_at_once(client):
    publisher = Publisher.objects.create(name="Old name")
    book = BookFactory(publisher=publisher)
    assert "Old name" in _page(client, book)

    publisher.name = "New name"
    publisher.save()

    assert "New name" in _page(client, book)


# ---------------------------------------------------------------------------
# seed_books
# ---------------------------------------------------------------------------


# Generated with AI
def test_seed_books_fills_the_details():
    call_command("seed_books", stdout=StringIO())

    hobbit = Book.objects.get(title="Хоббіт")
    assert hobbit.publisher.name == "Видавництво Старого Лева"
    assert (hobbit.cover_type, hobbit.language, hobbit.publication_year) == ("hard", "uk", 2019)
    trees = Book.objects.get(title="Таємне життя дерев")
    assert (trees.book_type, trees.cover_type, trees.pages) == ("audiobook", "", None)
    # Different values for the filters of the catalog
    assert set(Book.objects.values_list("book_type", flat=True)) == {"paper", "ebook", "audiobook"}
    assert set(Book.objects.values_list("language", flat=True)) == {"uk", "en"}


# Generated with AI
def test_seed_books_fills_only_the_empty_details_of_existing_books():
    author = AuthorFactory(name="Дж.Р. Толкін")
    # Seeded before the details existed: no details at all
    old = BookFactory(title="Хоббіт", author=author)
    # A manager has typed some details in: they stay
    edited = BookFactory(title="Володар перснів", author=author, language="en", pages=999)
    out = StringIO()

    call_command("seed_books", stdout=out)

    old.refresh_from_db()
    edited.refresh_from_db()
    assert (old.publisher.name, old.cover_type, old.pages) == (
        "Видавництво Старого Лева",
        "hard",
        304,
    )
    assert (edited.language, edited.pages) == ("en", 999)
    assert (edited.publisher.name, edited.cover_type) == ("Vivat", "dust_jacket")
    assert "+ details of Хоббіт" in out.getvalue()

    # A second run changes nothing
    again = StringIO()
    call_command("seed_books", stdout=again)
    assert "+ details" not in again.getvalue()
