"""The whole-response cache of /api/authors/ and /api/categories/ (api.cache).

A cached answer needs no SQL at all; any change of the catalog (an author,
a category, a book, a link book <-> category) is visible at once.
/api/books/ is not cached: it has the stock.
"""

import logging

import pytest

from tests.factories import AuthorFactory, BookFactory, CategoryFactory

pytestmark = pytest.mark.django_db


def names(response):
    return [item["name"] for item in response.json()["results"]]


# Generated with AI
@pytest.mark.parametrize("url", ["/api/authors/", "/api/categories/"])
def test_second_request_is_answered_from_the_cache_without_sql(
    api_client, django_assert_num_queries, url
):
    AuthorFactory(name="Lesya Ukrainka")
    CategoryFactory(name="Poetry")
    first = api_client.get(url)

    with django_assert_num_queries(0):
        second = api_client.get(url)

    assert second.status_code == 200
    assert second.json() == first.json()


# Generated with AI
def test_every_url_has_its_own_cached_answer(api_client):
    AuthorFactory(name="Lesya Ukrainka")
    AuthorFactory(name="Taras Shevchenko")

    assert names(api_client.get("/api/authors/")) == ["Lesya Ukrainka", "Taras Shevchenko"]
    assert names(api_client.get("/api/authors/?search=taras")) == ["Taras Shevchenko"]


# Generated with AI
def test_a_new_author_is_in_the_list_at_once(api_client):
    AuthorFactory(name="Lesya Ukrainka")
    api_client.get("/api/authors/")  # cached

    AuthorFactory(name="Taras Shevchenko")

    assert names(api_client.get("/api/authors/")) == ["Lesya Ukrainka", "Taras Shevchenko"]


# Generated with AI
def test_books_count_changes_at_once_when_a_book_is_added(api_client):
    poetry = CategoryFactory(name="Poetry")
    author = AuthorFactory(name="Taras Shevchenko")
    api_client.get("/api/categories/")
    api_client.get(f"/api/authors/{author.pk}/")

    BookFactory(author=author, categories=[poetry])

    assert api_client.get("/api/categories/").json()["results"][0]["books_count"] == 1
    assert api_client.get(f"/api/authors/{author.pk}/").json()["books_count"] == 1


# Generated with AI
def test_a_change_through_the_api_is_visible_at_once(as_user, manager):
    client = as_user(manager)
    category = CategoryFactory(name="Poetry", slug="poetry")
    assert names(client.get("/api/categories/")) == ["Poetry"]

    response = client.patch(f"/api/categories/{category.pk}/", {"name": "Poems"}, format="json")

    assert response.status_code == 200
    assert names(client.get("/api/categories/")) == ["Poems"]


# Generated with AI
def test_books_are_not_cached(api_client, django_assert_num_queries):
    BookFactory()
    api_client.get("/api/books/")

    # COUNT + books + categories + formats, every time: the stock must be fresh
    with django_assert_num_queries(4):
        api_client.get("/api/books/")


# Generated with AI
def test_api_cache_hits_misses_and_new_generations_are_logged(api_client, caplog):
    with caplog.at_level(logging.DEBUG, logger="api.cache"):
        api_client.get("/api/authors/")
        api_client.get("/api/authors/")
        AuthorFactory(name="Lesya Ukrainka")

    messages = [record.getMessage() for record in caplog.records if record.name == "api.cache"]
    assert any(m.startswith("API cache miss: /api/authors/") for m in messages)
    assert any(m.startswith("API cache hit: /api/authors/") for m in messages)
    assert "API cache: new generation, old answers are not used (Author saved)" in messages
