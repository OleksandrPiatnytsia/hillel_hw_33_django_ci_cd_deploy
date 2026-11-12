"""Integration: the catalog from the staff side - a manager and an editor
create, edit and delete books through the site forms (not the admin), with
the permissions of their groups (users/migrations/0003_create_groups.py):

- Managers: add, change, delete books, change the stock (inventory.change_stock);
- Editors:  add and change books, but no deleting and no stock.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from books.models import Book

from ..factories import AuthorFactory, BookFactory, CategoryFactory, OrderFactory, UserFactory
from ..helpers import message_levels

pytestmark = pytest.mark.django_db


@pytest.fixture
def editor_client(client):
    client.force_login(UserFactory(username="editor", groups=["Editors"]))
    return client


def book_form_data(author, **changes):
    data = {
        "title": "Kobzar",
        "author": author.pk,
        "price": "250.50",
        "stock": "7",
        "categories": [],
        "description": "Poems",
    }
    return {**data, **changes}


def test_manager_creates_edits_and_deletes_a_book(manager_client):
    author = AuthorFactory(name="Taras Shevchenko")
    poetry = CategoryFactory(name="Poetry", slug="poetry")

    # Create: the form page, then POST -> the new book's page
    assert manager_client.get(reverse("books:create")).status_code == 200
    created = manager_client.post(
        reverse("books:create"), book_form_data(author, categories=[poetry.pk])
    )
    book = Book.objects.get(title="Kobzar")
    assertRedirects(created, book.get_absolute_url(), fetch_redirect_response=False)
    assert (book.price, book.stock, list(book.categories.all())) == (Decimal("250.50"), 7, [poetry])

    # Edit: price and stock
    edited = manager_client.post(
        reverse("books:update", args=[book.pk]),
        book_form_data(author, price="300.00", stock="2"),
        follow=True,
    )
    book.refresh_from_db()
    assert (book.price, book.stock) == (Decimal("300.00"), 2)
    assert message_levels(edited)[-1] == "success"  # "created" is still in the list

    # Delete: the confirmation page shows the title and the button, POST deletes
    confirm = manager_client.get(reverse("books:delete", args=[book.pk]))
    assert "Kobzar" in confirm.content.decode()
    assert confirm.context["orders_count"] == 0
    assert 'class="btn btn-danger"' in confirm.content.decode()
    deleted = manager_client.post(reverse("books:delete", args=[book.pk]), follow=True)
    assertRedirects(deleted, reverse("books:list"))
    assert message_levels(deleted)[-1] == "success"
    assert not Book.objects.filter(pk=book.pk).exists()


def test_invalid_book_form_shows_errors_and_saves_nothing(manager_client):
    author = AuthorFactory()

    response = manager_client.post(
        reverse("books:create"), book_form_data(author, title="", price="-1")
    )

    assert response.status_code == 200  # the form again, not a redirect
    assert set(response.context["form"].errors) == {"title", "price"}
    assert not Book.objects.exists()


def test_editor_edits_a_book_but_cannot_change_the_stock(editor_client):
    book = BookFactory(title="Kobzar", stock=5)

    # The stock field is disabled for an editor: a POSTed value is ignored
    editor_client.post(
        reverse("books:update", args=[book.pk]),
        book_form_data(book.author, title="Kobzar (2nd ed.)", stock="999"),
    )

    book.refresh_from_db()
    assert book.title == "Kobzar (2nd ed.)"
    assert book.stock == 5


def test_editor_cannot_delete_a_book(editor_client):
    book = BookFactory()

    assert editor_client.post(reverse("books:delete", args=[book.pk])).status_code == 403
    assert Book.objects.filter(pk=book.pk).exists()


def test_a_book_in_orders_is_not_deleted_and_the_manager_sees_why(manager_client):
    # OrderItem.book: on_delete=PROTECT. Before the fix: 500 (ProtectedError)
    book = BookFactory(title="Kobzar")
    OrderFactory(items=[(book, 1)])
    OrderFactory(items=[(book, 2)])

    # The confirmation page warns at once and has no "Yes, delete" button
    confirm = manager_client.get(reverse("books:delete", args=[book.pk]))
    # POST anyway (an old open tab, or the book was ordered after the page
    # was opened): back to the book with the reason, the book stays
    deleted = manager_client.post(reverse("books:delete", args=[book.pk]), follow=True)

    assert confirm.context["orders_count"] == 2
    # No red "Yes, delete" button (its text is translated, so the button
    # is found by its class; the navbar has other submit buttons)
    assert 'class="btn btn-danger"' not in confirm.content.decode()
    assertRedirects(deleted, book.get_absolute_url())
    assert message_levels(deleted) == ["error"]
    assert Book.objects.filter(pk=book.pk).exists()


def test_author_page_lists_the_authors_books(client):
    author = AuthorFactory(name="Lesya Ukrainka")
    BookFactory(title="Lisova pisnia", author=author)
    BookFactory(title="Someone else's book")

    response = client.get(reverse("books:author_detail", args=[author.pk]))

    assert response.status_code == 200
    assert [book.title for book in response.context["books"]] == ["Lisova pisnia"]
