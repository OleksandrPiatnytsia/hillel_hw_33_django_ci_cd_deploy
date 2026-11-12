"""The catalog API: /api/books/, /api/authors/, /api/categories/.

Reading is open to everybody. Writing books follows the permissions of the
groups (Editors: add and change, Managers: also delete and the stock);
authors and categories need staff + the permission, like the admin.
"""

from decimal import Decimal

import pytest

from books.models import Author, Book, Category
from tests.factories import (
    AuthorFactory,
    BookFactory,
    CategoryFactory,
    OrderFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Books: reading, pagination, filters
# ---------------------------------------------------------------------------


def test_anonymous_reads_books_with_nested_author_and_categories(api_client):
    poetry = CategoryFactory(name="Poetry", slug="poetry")
    author = AuthorFactory(name="Taras Shevchenko")
    BookFactory(title="Kobzar", author=author, categories=[poetry], price=Decimal("250.50"))

    response = api_client.get("/api/books/")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    book = data["results"][0]
    assert book["title"] == "Kobzar"
    # Nested serializers: objects, not just ids
    assert book["author"] == {"id": author.pk, "name": "Taras Shevchenko"}
    assert book["categories"] == [{"id": poetry.pk, "name": "Poetry", "slug": "poetry"}]
    # Decimal as a string: no float rounding (250.5 vs 250.50)
    assert book["price"] == "250.50"
    assert book["in_stock"] is True
    assert book["cover"] is None
    # write-only fields are not in the answer
    assert "author_id" not in book and "category_ids" not in book


def test_books_are_paginated_by_20(api_client):
    BookFactory.create_batch(25)

    first = api_client.get("/api/books/").json()
    second = api_client.get(first["next"]).json()

    assert first["count"] == 25
    assert len(first["results"]) == 20
    assert first["previous"] is None
    assert len(second["results"]) == 5
    assert second["next"] is None


def test_book_list_takes_the_same_number_of_queries_for_any_page_size(
    api_client, django_assert_num_queries
):
    # COUNT for the paginator + the books with their authors (JOIN) + the
    # categories of the whole page (prefetch): 3, not 1 + 2 per book
    category = CategoryFactory()
    BookFactory.create_batch(15, categories=[category])

    with django_assert_num_queries(3):
        response = api_client.get("/api/books/")

    assert len(response.json()["results"]) == 15


def test_one_book_and_404_for_an_unknown_one(api_client):
    book = BookFactory(stock=0)

    found = api_client.get(f"/api/books/{book.pk}/")
    missing = api_client.get("/api/books/999999/")

    assert found.status_code == 200
    assert found.json()["id"] == book.pk
    assert found.json()["in_stock"] is False
    assert missing.status_code == 404


def test_cover_is_an_absolute_url(api_client):
    # Only the path is in the database; an API client gets the full address
    book = BookFactory(cover="covers/2026/11/kobzar.jpg")

    response = api_client.get(f"/api/books/{book.pk}/")

    assert response.json()["cover"] == "http://testserver/media/covers/2026/11/kobzar.jpg"


def titles(response):
    return [book["title"] for book in response.json()["results"]]


def test_book_filters_category_author_price_and_stock(api_client):
    poetry = CategoryFactory(slug="poetry")
    shevchenko = AuthorFactory(name="Taras Shevchenko")
    BookFactory(title="Kobzar", author=shevchenko, categories=[poetry], price=Decimal("300"))
    BookFactory(title="Haidamaky", author=shevchenko, price=Decimal("150"), stock=0)
    BookFactory(title="Zakhar Berkut", price=Decimal("200"), stock=3)

    assert titles(api_client.get("/api/books/?category=poetry")) == ["Kobzar"]
    assert titles(api_client.get(f"/api/books/?author={shevchenko.pk}")) == ["Haidamaky", "Kobzar"]
    assert titles(api_client.get("/api/books/?price_min=160&price_max=300")) == [
        "Kobzar",
        "Zakhar Berkut",
    ]
    assert titles(api_client.get("/api/books/?stock=out")) == ["Haidamaky"]
    assert titles(api_client.get("/api/books/?stock=low")) == ["Zakhar Berkut"]


def test_book_search_and_ordering(api_client):
    shevchenko = AuthorFactory(name="Taras Shevchenko")
    BookFactory(title="Kobzar", author=shevchenko, price=Decimal("300"))
    BookFactory(title="Haidamaky", author=shevchenko, price=Decimal("150"))
    BookFactory(title="Zakhar Berkut", price=Decimal("200"))

    # ?search= looks in the title and in the author's name
    assert titles(api_client.get("/api/books/?search=kobz")) == ["Kobzar"]
    assert titles(api_client.get("/api/books/?search=shevchenko")) == ["Haidamaky", "Kobzar"]
    assert titles(api_client.get("/api/books/?ordering=-price")) == [
        "Kobzar",
        "Zakhar Berkut",
        "Haidamaky",
    ]


def test_books_with_equal_price_keep_a_stable_order(api_client):
    # The same price for all: without "pk" at the end of the ORDER BY the
    # database may return them in a different order on every query
    books = BookFactory.create_batch(5, price=Decimal("100"))

    response = api_client.get("/api/books/?ordering=price")

    assert [book["id"] for book in response.json()["results"]] == [book.pk for book in books]


@pytest.mark.parametrize(
    "query, field",
    [
        ("price_min=500&price_max=100", "price_min"),
        ("category=no-such-category", "category"),
        ("price_min=abc", "price_min"),
    ],
)
def test_wrong_filter_values_are_400(api_client, query, field):
    response = api_client.get(f"/api/books/?{query}")

    assert response.status_code == 400
    assert field in response.json()


# ---------------------------------------------------------------------------
# Books: writing and permissions
# ---------------------------------------------------------------------------


def new_book_data(author, categories=(), **changes):
    data = {
        "title": "Kobzar",
        "author_id": author.pk,
        "category_ids": [category.pk for category in categories],
        "price": "250.50",
        "description": "Poems",
    }
    return {**data, **changes}


def test_anonymous_cannot_create_a_book(api_client):
    response = api_client.post("/api/books/", new_book_data(AuthorFactory()), format="json")

    # 401, not 403: with a token the request could pass
    assert response.status_code == 401
    assert not Book.objects.exists()


def test_customer_cannot_create_a_book(as_user, customer):
    response = as_user(customer).post("/api/books/", new_book_data(AuthorFactory()), format="json")

    assert response.status_code == 403
    assert not Book.objects.exists()


def test_editor_creates_a_book_with_a_jwt_token(api_client, editor, get_tokens):
    # The whole way of an external client: token -> Bearer header -> POST
    author = AuthorFactory(name="Taras Shevchenko")
    poetry = CategoryFactory(name="Poetry")
    access = get_tokens(editor)["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    response = api_client.post(
        "/api/books/", new_book_data(author, categories=[poetry]), format="json"
    )

    assert response.status_code == 201
    book = Book.objects.get()
    assert book.title == "Kobzar"
    assert book.author == author
    assert list(book.categories.all()) == [poetry]
    # The default stock: an editor doesn't set it
    assert book.stock == 0
    # The answer is the new book in the reading format (nested author)
    assert response.json()["author"]["name"] == "Taras Shevchenko"


def test_editor_cannot_set_the_stock_of_a_new_book(as_user, editor):
    response = as_user(editor).post(
        "/api/books/", new_book_data(AuthorFactory(), stock=50), format="json"
    )

    assert response.status_code == 403
    assert not Book.objects.exists()


def test_editor_changes_the_price_but_not_the_stock(as_user, editor):
    book = BookFactory(price=Decimal("100"), stock=10)
    client = as_user(editor)

    price = client.patch(f"/api/books/{book.pk}/", {"price": "120.00"}, format="json")
    stock = client.patch(f"/api/books/{book.pk}/", {"stock": 99}, format="json")
    # PUT with everything read before, the unchanged stock included: allowed
    full = client.get(f"/api/books/{book.pk}/").json()
    put = client.put(
        f"/api/books/{book.pk}/",
        {**full, "title": "New title", "author_id": book.author_id, "category_ids": []},
        format="json",
    )

    assert price.status_code == 200
    assert stock.status_code == 403
    assert put.status_code == 200
    book.refresh_from_db()
    assert book.price == Decimal("120.00")
    assert book.stock == 10
    assert book.title == "New title"


def test_manager_changes_the_stock(as_user, manager):
    book = BookFactory(stock=10)

    response = as_user(manager).patch(f"/api/books/{book.pk}/", {"stock": 3}, format="json")

    assert response.status_code == 200
    book.refresh_from_db()
    assert book.stock == 3


# Generated with AI
def test_manager_creates_a_book_with_its_first_copies(as_user, manager):
    response = as_user(manager).post(
        "/api/books/", new_book_data(AuthorFactory(), stock=7), format="json"
    )

    assert response.status_code == 201
    assert response.json()["stock"] == 7
    # Written to the default warehouse (inventory.Stock), not to the book
    assert Book.objects.get().stocks.get().quantity == 7


def test_invalid_book_data_is_400_with_the_errors_of_the_fields(as_user, editor):
    response = as_user(editor).post(
        "/api/books/",
        {"title": "", "author_id": 999999, "price": "-1"},
        format="json",
    )

    assert response.status_code == 400
    assert set(response.json()) == {"title", "author_id", "price"}


def test_only_manager_deletes_a_book(as_user, editor, manager):
    book = BookFactory()

    by_editor = as_user(editor).delete(f"/api/books/{book.pk}/")
    by_manager = as_user(manager).delete(f"/api/books/{book.pk}/")

    assert by_editor.status_code == 403
    assert by_manager.status_code == 204
    assert not Book.objects.exists()


def test_a_book_in_an_order_cannot_be_deleted(as_user, manager):
    # OrderItem.book: on_delete=PROTECT. 409 Conflict, not 500
    book = BookFactory()
    OrderFactory(items=[(book, 1)])

    response = as_user(manager).delete(f"/api/books/{book.pk}/")

    assert response.status_code == 409
    assert Book.objects.filter(pk=book.pk).exists()


# ---------------------------------------------------------------------------
# Authors and categories
# ---------------------------------------------------------------------------


def test_anonymous_reads_authors_and_categories_with_books_count(api_client):
    poetry = CategoryFactory(name="Poetry")
    author = AuthorFactory(name="Taras Shevchenko")
    BookFactory.create_batch(2, author=author, categories=[poetry])
    AuthorFactory(name="Lesya Ukrainka")

    authors = api_client.get("/api/authors/?ordering=-books_count").json()["results"]
    categories = api_client.get("/api/categories/").json()["results"]

    assert [(a["name"], a["books_count"]) for a in authors] == [
        ("Taras Shevchenko", 2),
        ("Lesya Ukrainka", 0),
    ]
    assert categories[0]["books_count"] == 2
    assert api_client.get("/api/authors/?search=lesya").json()["count"] == 1


@pytest.mark.parametrize("url", ["/api/authors/", "/api/categories/"])
def test_anonymous_cannot_write_authors_and_categories(api_client, url):
    # IsAdminUser for an anonymous user: 401 (with a token it could pass)
    response = api_client.post(url, {"name": "New", "slug": "new"}, format="json")

    assert response.status_code == 401


def test_editor_without_staff_cannot_add_an_author(as_user, editor):
    # Editors have add_author, but IsAdminUser (like the admin) wants is_staff
    response = as_user(editor).post("/api/authors/", {"name": "New Author"}, format="json")

    assert response.status_code == 403
    assert not Author.objects.filter(name="New Author").exists()


def test_staff_without_the_permission_cannot_add_a_category(as_user):
    staff_without_groups = UserFactory(username="intern", is_staff=True)

    response = as_user(staff_without_groups).post(
        "/api/categories/", {"name": "Drama", "slug": "drama"}, format="json"
    )

    assert response.status_code == 403


def test_manager_manages_categories_and_authors(as_user, manager):
    client = as_user(manager)

    created = client.post("/api/categories/", {"name": "Drama", "slug": "drama"}, format="json")
    duplicate = client.post("/api/categories/", {"name": "Drama", "slug": "drama"}, format="json")
    category = Category.objects.get(slug="drama")
    renamed = client.patch(f"/api/categories/{category.pk}/", {"name": "Plays"}, format="json")
    author = client.post("/api/authors/", {"name": "Ivan Franko", "bio": "Writer"}, format="json")

    assert created.status_code == 201
    assert created.json()["books_count"] == 0
    # unique=True of the model -> the serializer checks it: 400, not 500
    assert duplicate.status_code == 400
    assert renamed.status_code == 200
    assert author.status_code == 201
    category.refresh_from_db()
    assert category.name == "Plays"


def test_category_and_author_with_books_cannot_be_deleted(as_user, manager):
    # BookCategory.category and Book.author: on_delete=PROTECT -> 409
    category = CategoryFactory()
    author = AuthorFactory()
    BookFactory(author=author, categories=[category])
    empty_category = CategoryFactory()
    client = as_user(manager)

    assert client.delete(f"/api/categories/{category.pk}/").status_code == 409
    assert client.delete(f"/api/authors/{author.pk}/").status_code == 409
    assert client.delete(f"/api/categories/{empty_category.pk}/").status_code == 204
    assert Category.objects.filter(pk=category.pk).exists()
    assert Author.objects.filter(pk=author.pk).exists()


def test_api_root_lists_the_sections(api_client):
    response = api_client.get("/api/")

    assert set(response.json()) == {"books", "authors", "categories", "orders"}


def test_api_errors_come_in_the_language_of_the_request(as_user, manager):
    # LocaleMiddleware: the Accept-Language header (no cookie in an API
    # client); without it - LANGUAGE_CODE, Ukrainian
    category = CategoryFactory()
    BookFactory(categories=[category])
    client = as_user(manager)

    default = client.delete(f"/api/categories/{category.pk}/")
    english = client.delete(f"/api/categories/{category.pk}/", HTTP_ACCEPT_LANGUAGE="en")

    assert default.json() == {"detail": "У категорії є книги, її не можна видалити."}
    assert english.json() == {"detail": "The category has books and can't be deleted."}
