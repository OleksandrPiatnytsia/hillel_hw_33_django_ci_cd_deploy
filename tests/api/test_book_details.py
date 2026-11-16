"""The details of the edition in the API: the fields of a book, the
filters of /api/books/ and the endpoint /api/publishers/."""

import pytest

from books.models import Book, Publisher
from tests.factories import BookFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def folio():
    return Publisher.objects.get(name="Фоліо")


# Generated with AI
def test_a_book_has_its_details(api_client, folio):
    BookFactory(
        publisher=folio,
        cover_type="hard",
        language="uk",
        publication_year=2017,
        pages=224,
    )

    book = api_client.get("/api/books/").json()["results"][0]

    assert book["publisher"] == {"id": folio.pk, "name": "Фоліо"}
    assert (book["language"], book["publication_year"]) == ("uk", 2017)
    # The type, the cover and the pages belong to the format
    paper = book["formats"][0]
    assert (paper["format_type"], paper["cover_type"], paper["pages"]) == ("paper", "hard", 224)
    assert "publisher_id" not in book  # write only


# Generated with AI
def test_a_book_without_details_has_nulls_and_empty_codes(api_client):
    BookFactory()

    book = api_client.get("/api/books/").json()["results"][0]

    assert book["publisher"] is None
    assert (book["language"], book["publication_year"]) == ("", None)
    assert (book["formats"][0]["cover_type"], book["formats"][0]["pages"]) == ("", None)


# Generated with AI
@pytest.mark.parametrize(
    "query, expected",
    [
        ("language=en", ["B", "C"]),
        ("language=uk&language=en", ["A", "B", "C"]),
        ("book_type=ebook", ["C"]),
        ("cover_type=hard", ["A"]),
        ("year_min=2015&year_max=2020", ["B"]),
    ],
)
def test_books_filtered_by_the_details(api_client, query, expected):
    BookFactory(title="A", language="uk", cover_type="hard", publication_year=2010)
    BookFactory(title="B", language="en", publication_year=2018)
    BookFactory(title="C", language="en", book_type="ebook", publication_year=2022)

    results = api_client.get(f"/api/books/?{query}").json()["results"]

    assert [book["title"] for book in results] == expected


# Generated with AI
def test_books_filtered_by_a_publisher_without_books_are_empty_not_an_error(api_client):
    BookFactory()
    vivat = Publisher.objects.get(name="Vivat")

    response = api_client.get(f"/api/books/?publisher={vivat.pk}")

    # The API accepts every publisher; the site offers only those with books
    assert response.status_code == 200
    assert response.json()["count"] == 0


# Generated with AI
@pytest.mark.parametrize(
    "query, field",
    [
        ("year_min=2020&year_max=2010", "year_min"),
        ("language=xx", "language"),
        ("cover_type=leather", "cover_type"),
    ],
)
def test_wrong_filter_values_are_400(api_client, query, field):
    response = api_client.get(f"/api/books/?{query}")

    assert response.status_code == 400
    assert field in response.json()


# Generated with AI
def test_editor_creates_a_book_with_details(as_user, editor, folio):
    author = BookFactory().author

    response = as_user(editor).post(
        "/api/books/",
        {
            "title": "Kobzar",
            "author_id": author.pk,
            "publisher_id": folio.pk,
            "language": "uk",
            "publication_year": 2015,
        },
        format="json",
    )

    assert response.status_code == 201, response.json()
    book = Book.objects.get(title="Kobzar")
    assert (book.publisher, book.language, book.publication_year) == (folio, "uk", 2015)


# Generated with AI
def test_a_future_publication_year_is_400(as_user, editor):
    book = BookFactory()

    response = as_user(editor).patch(
        f"/api/books/{book.pk}/", {"publication_year": 3000}, format="json"
    )

    assert response.status_code == 400
    assert "publication_year" in response.json()


# Generated with AI
def test_publishers_list_with_books_count(api_client, folio):
    BookFactory(publisher=folio)

    response = api_client.get("/api/publishers/?search=Фол")

    assert response.status_code == 200
    assert response.json()["results"] == [{"id": folio.pk, "name": "Фоліо", "books_count": 1}]


# Generated with AI
def test_publishers_are_written_by_staff_only(as_user, editor, manager):
    assert as_user(editor).post("/api/publishers/", {"name": "New"}).status_code == 403

    response = as_user(manager).post("/api/publishers/", {"name": "New"})

    assert response.status_code == 201
    assert Publisher.objects.filter(name="New").exists()


# Generated with AI
def test_a_publisher_with_books_is_not_deleted(as_user, manager, folio):
    BookFactory(publisher=folio)

    response = as_user(manager).delete(f"/api/publishers/{folio.pk}/")

    assert response.status_code == 409


# Generated with AI
def test_the_publishers_list_is_cached_and_dropped_on_a_change(api_client, folio):
    first = api_client.get("/api/publishers/?search=Фол").json()
    folio.name = "Фоліо (нове)"
    folio.save()

    second = api_client.get("/api/publishers/?search=Фол").json()

    assert first["results"][0]["name"] == "Фоліо"
    assert second["results"][0]["name"] == "Фоліо (нове)"
