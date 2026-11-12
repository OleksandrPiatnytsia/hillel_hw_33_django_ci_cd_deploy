"""Integration: the cache of the book pages (books.cache, books.signals).

The tests use LocMemCache (config/settings/test.py), emptied before every
test (conftest.py); the rules are the same as with Redis.

What must hold:
- a cached book page needs fewer queries, but the stock is always fresh;
- every change of the book, its author or its categories is visible at once;
- cached HTML never carries one visitor's data to another: CSRF token,
  manager buttons, language.
"""

import logging
import re

import pytest
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from books.cache import book_key
from books.models import BookCategory
from inventory.services import set_stock
from orders.services import create_order

from ..factories import AuthorFactory, BookFactory, CategoryFactory, UserFactory

pytestmark = pytest.mark.django_db

COOKIE = settings.LANGUAGE_COOKIE_NAME


@pytest.fixture
def book():
    return BookFactory(
        title="Kobzar",
        author=AuthorFactory(name="Taras Shevchenko"),
        categories=[CategoryFactory(name="Poetry", slug="poetry")],
        stock=5,
    )


def page(client, book):
    return client.get(reverse("books:detail", args=[book.pk])).content.decode()


def catalog(client):
    return client.get(reverse("books:list")).content.decode()


def queries_of(client, url):
    with CaptureQueriesContext(connection) as queries:
        assert client.get(url).status_code == 200
    return [query["sql"] for query in queries]


# Generated with AI
def test_second_visit_of_a_book_page_reads_the_book_from_the_cache(client, book):
    url = reverse("books:detail", args=[book.pk])
    first = queries_of(client, url)
    assert cache.get(book_key(book.pk)) is not None
    second = queries_of(client, url)

    # The book with its author (JOIN) and its categories: only the first time
    assert any('"books_category"' in sql for sql in first)
    assert not any('"books_category"' in sql for sql in second)
    assert not any('FROM "books_book"' in sql for sql in second)
    # The stock: every time
    assert any('"inventory_stock"' in sql for sql in second)


# Generated with AI
def test_the_stock_is_fresh_while_the_book_is_cached(client, book):
    assert 'max="5"' in page(client, book)

    create_order(
        UserFactory(), {book.pk: 3}, full_name="Ann", phone="+380671234567", address="Kyiv"
    )

    html = page(client, book)
    assert 'max="2"' in html  # the quantity field: at most the 2 left
    assert 'max="5"' not in html


# Generated with AI
def test_a_new_title_is_shown_at_once(client, book):
    page(client, book)
    catalog(client)  # both cached now

    book.title = "Kobzar (2nd ed.)"
    book.save()

    assert "Kobzar (2nd ed.)" in page(client, book)
    assert "Kobzar (2nd ed.)" in catalog(client)


# Generated with AI
def test_a_renamed_author_is_shown_at_once(client, book):
    page(client, book)
    catalog(client)

    author = book.author
    author.name = "T. H. Shevchenko"
    author.save()

    assert "T. H. Shevchenko" in page(client, book)
    assert "T. H. Shevchenko" in catalog(client)


# Generated with AI
def test_a_renamed_category_is_shown_at_once(client, book):
    page(client, book)
    catalog(client)

    category = book.categories.get()
    category.name = "Poems"
    category.save()

    assert "Poems" in page(client, book)
    assert "Poems" in catalog(client)


# Generated with AI
@pytest.mark.parametrize("how", ["set", "category_side", "link_object", "clear"])
def test_changed_categories_are_shown_at_once(client, book, how):
    page(client, book)
    drama = CategoryFactory(name="Drama", slug="drama")

    if how == "set":  # the book form and the API
        book.categories.set([drama])
    elif how == "category_side":  # category.books.add(...)
        drama.books.add(book)
    elif how == "link_object":  # the admin inlines save BookCategory rows
        BookCategory.objects.create(book=book, category=drama)
    else:  # from the category's side, everything at once
        book.categories.get().books.clear()

    html = page(client, book)
    if how == "clear":
        assert "Poetry" not in html
    else:
        assert "Drama" in html


# Generated with AI
def test_cached_fragments_carry_no_csrf_token_or_buttons_of_another_user(
    manager_client, customer, other_customer, book
):
    edit_url = reverse("books:update", args=[book.pk])
    # The manager is the first visitor: the fragments are made on his visit
    assert edit_url in page(manager_client, book)

    # enforce_csrf_checks: the test client skips the CSRF check by default
    clients = [Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)]
    clients[0].force_login(customer)
    clients[1].force_login(other_customer)
    pages = [page(c, book) for c in clients]

    # No manager buttons for the customers
    assert all(edit_url not in html for html in pages)
    tokens = [
        re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1) for html in pages
    ]
    # Every page has its own token (a token from the cache would be the
    # same string in every page) and it works: the form is accepted
    assert tokens[0] != tokens[1]
    for c, token in zip(clients, tokens, strict=True):
        response = c.post(
            reverse("cart:add", args=[book.pk]), {"quantity": 1, "csrfmiddlewaretoken": token}
        )
        assert response.status_code == 302  # 403 with someone else's token


# Generated with AI
def test_every_language_has_its_own_cached_fragment(client, book):
    client.cookies[COOKIE] = "uk"
    assert "Обкладинка «Kobzar»" in page(client, book)

    client.cookies[COOKIE] = "en"
    english = page(client, book)
    assert "Cover of Kobzar" in english
    assert "Обкладинка" not in english


# Generated with AI
def test_set_stock_needs_no_cache_invalidation(client, book):
    page(client, book)
    set_stock(book, 1)

    # The cached book stays (no stock in it), the page shows the new stock
    assert cache.get(book_key(book.pk)) is not None
    assert 'max="1"' in page(client, book)


# Generated with AI
def test_unknown_book_is_404(client):
    assert client.get(reverse("books:detail", args=[999999])).status_code == 404


# Generated with AI
def test_cache_hits_misses_and_clearing_are_logged(client, book, caplog):
    with caplog.at_level(logging.DEBUG, logger="books.cache"):
        page(client, book)
        page(client, book)
        book.title = "Kobzar (2nd ed.)"
        book.save()

    messages = [record.getMessage() for record in caplog.records if record.name == "books.cache"]
    assert f"Book cache miss: id={book.pk}, cached for {settings.BOOK_CACHE_TIMEOUT} s" in messages
    assert f"Book cache hit: id={book.pk}" in messages
    assert f"Book cache cleared: ids=[{book.pk}] (7 keys), reason: Book saved" in messages
