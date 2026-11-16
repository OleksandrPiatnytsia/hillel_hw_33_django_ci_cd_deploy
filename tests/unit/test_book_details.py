"""The details of the edition: publisher, language, year (the cover and the pages: of the formats).

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
from books.forms import BookForm, BookFormatForm
from books.models import Book, BookFormat, Publisher

from ..factories import AuthorFactory, BookFactory
from ..helpers import format_row

pytestmark = pytest.mark.django_db


# Generated with AI
def test_a_book_without_details_is_valid():
    book = BookFactory()

    book.full_clean()

    assert book.publisher is None
    assert book.language == ""
    assert book.publication_year is None


# Generated with AI
def test_all_details_are_saved_and_shown_with_their_labels():
    publisher = Publisher.objects.get(name="Видавництво Старого Лева")
    book = BookFactory(
        publisher=publisher,
        language=Book.Language.UKRAINIAN,
        publication_year=2020,
        # The cover and the pages are of the format
        cover_type=BookFormat.CoverType.DUST_JACKET,
        pages=352,
    )

    book.full_clean()
    book.refresh_from_db()

    assert book.publisher == publisher
    paper = book.formats.get()
    with translation.override("en"):
        assert paper.get_cover_type_display() == "Dust jacket"
        assert book.get_language_display() == "Ukrainian"
    assert (book.publication_year, paper.pages) == (2020, 352)


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
    paper = BookFactory(pages=pages).formats.get()

    if valid:
        paper.full_clean()
    else:
        with pytest.raises(ValidationError):
            paper.full_clean()


# Generated with AI
def test_a_publisher_with_books_cannot_be_deleted():
    publisher = Publisher.objects.create(name="Test publisher")
    BookFactory(publisher=publisher)

    with pytest.raises(ProtectedError):
        publisher.delete()


# Generated with AI
def test_publishers_are_ordered_by_name_and_shown_by_name():
    names = list(Publisher.objects.values_list("name", flat=True))

    # Without order_by() the list comes in Meta.ordering = ["name"].
    # Where Cyrillic and Latin go depends on the collation of the database
    # (local Docker: Cyrillic first, Postgres of CI: Latin first), so the
    # test compares with the database's own sort, not with fixed names
    assert Publisher._meta.ordering == ["name"]
    assert names == list(Publisher.objects.order_by("name").values_list("name", flat=True))
    # Inside one alphabet the order is the same in every collation
    assert names.index("А-БА-БА-ГА-ЛА-МА-ГА") < names.index("Ранок")
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
    for field in ["publisher", "language", "publication_year"]:
        assert f'name="{field}"' in content, field
    # The type, the cover and the pages: in the rows of the formats
    for field in ["format_type", "cover_type", "pages"]:
        assert f'name="formats-0-{field}"' in content, field


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
        "description": "",
    }
    return {**data, **changes}


# Generated with AI
def test_book_form_saves_the_details():
    publisher = Publisher.objects.get(name="Ранок")
    form = BookForm(data=_form_data(publisher=publisher.pk, language="pl", publication_year="2015"))

    assert form.is_valid(), form.errors
    book = form.save()

    assert (book.publisher, book.language, book.publication_year) == (publisher, "pl", 2015)


# Generated with AI
def test_book_form_details_are_optional():
    form = BookForm(data=_form_data())

    assert form.is_valid(), form.errors
    # The type, the cover, the pages and the price belong to the formats
    for name in ["book_type", "cover_type", "pages", "price", "currency"]:
        assert name not in form.fields, name


# Generated with AI
def test_format_form_shows_the_cover_error_of_an_ebook_under_the_cover_field():
    form = BookFormatForm(data=format_row("ebook", cover_type="hard"))

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
    # The details, then the formats, then the cover
    assert (
        content.index('name="publication_year"')
        < content.index('name="formats-0-format_type"')
        < content.index('name="cover"')
    )


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
    for text in ["Details", "Hardcover", "English", "Formats", "Paper"]:
        assert text in content, text


# Generated with AI
def test_book_page_hides_unknown_details(client):
    book = BookFactory()

    content = _page(client, book, "en")

    # Only the formats: the other details are not known
    assert '<dt class="col-sm-4 col-lg-3">Formats</dt>' in content
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
    assert (hobbit.language, hobbit.publication_year) == ("uk", 2019)
    # Different values for the filters of the catalog
    assert set(Book.objects.values_list("language", flat=True)) == {"uk", "en"}
    assert Book.objects.filter(publisher__isnull=True).count() == 1  # "Воно"


# Generated with AI
def test_seed_books_fills_only_the_empty_details_of_existing_books():
    author = AuthorFactory(name="Дж.Р. Толкін")
    # Seeded before the details existed: no details at all
    old = BookFactory(title="Хоббіт", author=author)
    # A manager has typed some details in: they stay
    edited = BookFactory(title="Володар перснів", author=author, language="en")
    out = StringIO()

    call_command("seed_books", stdout=out)

    old.refresh_from_db()
    edited.refresh_from_db()
    assert (old.publisher.name, old.language, old.publication_year) == (
        "Видавництво Старого Лева",
        "uk",
        2019,
    )
    assert (edited.publisher.name, edited.language) == ("Vivat", "en")
    assert "+ details of Хоббіт" in out.getvalue()

    # A second run changes nothing
    again = StringIO()
    call_command("seed_books", stdout=again)
    assert "+ details" not in again.getvalue()


# ---------------------------------------------------------------------------
# The catalog: filters of the details, the panel, the chips (stage 3)
# ---------------------------------------------------------------------------


def _catalog(client, params=None, language="uk"):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    return client.get(reverse("books:list"), params or {})


def _titles(response):
    return [book.title for book in response.context["books"]]


@pytest.fixture
def editions():
    """Four books with different details, one without any."""
    folio, ranok = Publisher.objects.get(name="Фоліо"), Publisher.objects.get(name="Ранок")
    return {
        "A": BookFactory(
            title="A",
            publisher=folio,
            language="uk",
            cover_type="hard",
            publication_year=2010,
        ),
        "B": BookFactory(title="B", publisher=ranok, language="en", publication_year=2018),
        "C": BookFactory(
            title="C", publisher=folio, language="en", format_type="ebook", publication_year=2022
        ),
        "D": BookFactory(title="D"),
    }


# Generated with AI
@pytest.mark.parametrize(
    "params, expected",
    [
        ({"publisher": "folio"}, ["A", "C"]),
        ({"language": "en"}, ["B", "C"]),
        ({"language": ["uk", "en"]}, ["A", "B", "C"]),  # OR inside a filter
        ({"book_type": "ebook"}, ["C"]),
        ({"cover_type": "hard"}, ["A"]),
        ({"year_min": "2015"}, ["B", "C"]),
        ({"year_max": "2018"}, ["A", "B"]),
        ({"year_min": "2011", "year_max": "2020"}, ["B"]),
        ({"publisher": "folio", "language": "en"}, ["C"]),  # AND between filters
    ],
)
def test_catalog_filters_by_the_details(client, editions, params, expected):
    folio = Publisher.objects.get(name="Фоліо")
    if params.get("publisher") == "folio":
        params = {**params, "publisher": folio.pk}

    assert _titles(_catalog(client, params)) == expected


# Generated with AI
def test_catalog_panel_offers_only_the_values_books_have(client, editions):
    form = _catalog(client).context["filter_form"]

    publishers = [publisher.name for publisher in form.fields["publisher"].queryset]
    assert publishers == ["Ранок", "Фоліо"]  # not all 32 of the migration
    assert [value for value, _label in form.fields["language"].choices] == ["uk", "en"]
    assert [value for value, _label in form.fields["book_type"].choices] == ["paper", "ebook"]
    assert [value for value, _label in form.fields["cover_type"].choices] == ["hard"]


# Generated with AI
def test_catalog_panel_has_the_blocks_in_the_language_of_the_site(client, editions):
    content = _catalog(client).content.decode()

    for text in ["Видавництво", "Мова", "Формат", "Обкладинка", "Рік видання", "Тверда"]:
        assert text in content, text
    # The year block: the oldest and the newest edition as hints
    assert 'placeholder="2010"' in content and 'placeholder="2022"' in content


# Generated with AI
def test_catalog_panel_hides_the_blocks_without_values(client):
    BookFactory()  # no details at all, only its paper format

    content = _catalog(client, language="en").content.decode()

    assert 'id="filter-publisher"' not in content
    assert 'id="filter-language"' not in content
    assert 'id="filter-cover_type"' not in content
    assert 'id="filter-year"' not in content
    # A book on sale always has a format
    assert 'id="filter-book_type"' in content


# Generated with AI
def test_catalog_chips_of_the_details(client, editions):
    folio = Publisher.objects.get(name="Фоліо")

    response = _catalog(
        client,
        {
            "publisher": folio.pk,
            "language": ["uk", "en"],
            "cover_type": "hard",
            "year_min": "2005",
            "year_max": "2020",
        },
    )
    chips = {chip["label"]: chip["url"] for chip in response.context["filter_chips"]}

    assert list(chips) == [
        "Фоліо",
        "Українська",
        "Англійська",
        "Тверда",
        "Рік: 2005–2020",
    ]
    assert chips["Англійська"] == (
        f"?publisher={folio.pk}&language=uk&cover_type=hard&year_min=2005&year_max=2020"
    )
    assert (
        chips["Рік: 2005–2020"] == f"?publisher={folio.pk}&language=uk&language=en&cover_type=hard"
    )


# Generated with AI
@pytest.mark.parametrize(
    "params, label",
    [({"year_min": "2015"}, "Рік: від 2015"), ({"year_max": "2015"}, "Рік: до 2015")],
)
def test_catalog_chip_of_one_end_of_the_year_range(client, editions, params, label):
    chips = [chip["label"] for chip in _catalog(client, params).context["filter_chips"]]

    assert chips == [label]


# Generated with AI
def test_catalog_skips_a_wrong_year_range_and_shows_why(client, editions):
    response = _catalog(client, {"year_min": "2020", "year_max": "2010", "language": "en"})

    # The other filters still work, the range is ignored
    assert _titles(response) == ["B", "C"]
    assert "«Рік від» не може бути більшим за «Рік до»." in response.content.decode()


# Generated with AI
def test_catalog_shows_an_error_for_a_publisher_without_books(client, editions):
    lonely = Publisher.objects.get(name="Vivat")  # no book has it

    response = _catalog(client, {"publisher": lonely.pk})

    assert "publisher" in response.context["filter_form"].errors
    assert response.context["filter_chips"] == []


# Generated with AI
def test_book_page_links_the_publisher_to_the_filtered_catalog(client, editions):
    book = editions["A"]

    content = _page(client, book)

    assert f'href="{reverse("books:list")}?publisher={book.publisher.pk}"' in content
