"""Unit tests of inventory: warehouses, Stock rows, book.stock, the rights.

The stock moved from the column Book.stock to inventory.Stock (hw_31).
The tests of orders, the cart and the API check that nothing changed for
the user; these check the new parts themselves.
"""

import pytest
from django.db import IntegrityError

from books.forms import BookForm
from books.models import Book
from inventory.models import Stock, Warehouse
from inventory.services import return_to_stock, set_stock
from orders.services import cancel_order, create_order

from ..factories import AuthorFactory, BookFactory, UserFactory

pytestmark = pytest.mark.django_db


# Generated with AI
def test_data_migration_made_the_default_warehouse():
    warehouse = Warehouse.objects.get(is_default=True)

    assert (warehouse.name, warehouse.slug) == ("General", "general")
    assert Warehouse.objects.get_default() == warehouse


# Generated with AI
def test_only_one_warehouse_can_be_the_default():
    with pytest.raises(IntegrityError):
        Warehouse.objects.create(name="Second", slug="second", is_default=True)


# Generated with AI
def test_a_new_book_gets_a_stock_row_with_zero():
    book = Book.objects.create(title="New", author=AuthorFactory(), price="100.00")

    stock = Stock.objects.get(book=book)
    assert (stock.warehouse.is_default, stock.quantity) == (True, 0)
    assert book.stock == 0


# Generated with AI
def test_one_row_per_book_per_warehouse():
    book = BookFactory()

    with pytest.raises(IntegrityError):
        Stock.objects.create(book=book, warehouse=Warehouse.objects.get_default())


# Generated with AI
def test_stock_can_not_go_below_zero_in_the_database():
    book = BookFactory(stock=1)

    # PositiveIntegerField -> CHECK (quantity >= 0) in PostgreSQL
    with pytest.raises(IntegrityError):
        Stock.objects.filter(book=book).update(quantity=-1)


# Generated with AI
def test_with_stock_reads_the_stock_of_a_whole_list_in_one_query(django_assert_num_queries):
    BookFactory(stock=3)
    BookFactory(stock=0)
    BookFactory(stock=7)

    with django_assert_num_queries(1):
        stocks = sorted(book.stock for book in Book.objects.with_stock())

    assert stocks == [0, 3, 7]


# Generated with AI
def test_with_stock_counts_only_the_default_warehouse():
    book = BookFactory(stock=2)
    other = Warehouse.objects.create(name="Lviv", slug="lviv")
    set_stock(book, 50, warehouse=other)

    assert Book.objects.with_stock().get(pk=book.pk).stock == 2


# Generated with AI
def test_book_without_annotation_reads_stock_once_and_refresh_resets_it(django_assert_num_queries):
    book = Book.objects.get(pk=BookFactory(stock=4).pk)

    with django_assert_num_queries(1):
        assert (book.stock, book.stock) == (4, 4)  # the second read: no query

    Stock.objects.filter(book=book).update(quantity=9)
    book.refresh_from_db()
    assert book.stock == 9


# Generated with AI
def test_return_to_stock_adds_in_sql_and_recreates_a_missing_row():
    book = BookFactory(stock=2)
    warehouse = Warehouse.objects.get_default()

    return_to_stock(book.pk, 3, warehouse)
    assert Stock.objects.get(book=book).quantity == 5

    Stock.objects.filter(book=book).delete()
    return_to_stock(book.pk, 1, warehouse)
    assert Stock.objects.get(book=book).quantity == 1


# Generated with AI
def test_order_takes_and_cancel_returns_the_copies_of_the_default_warehouse():
    book = BookFactory(stock=5)
    order = create_order(
        UserFactory(), {book.pk: 2}, full_name="Ann", phone="+380671234567", address="Kyiv"
    )
    assert Stock.objects.get(book=book).quantity == 3

    cancel_order(order.pk)
    assert Stock.objects.get(book=book).quantity == 5


# ---------------------------------------------------------------------------
# Rights: books.manage_stock -> inventory.change_stock (migration 0003)
# ---------------------------------------------------------------------------


# Generated with AI
@pytest.mark.parametrize(
    ("group", "can_change", "can_view"),
    [("Managers", True, True), ("Editors", False, True), ("Customers", False, False)],
)
def test_stock_permissions_of_the_groups(group, can_change, can_view):
    user = UserFactory(groups=[group])

    assert user.has_perm("inventory.change_stock") is can_change
    assert user.has_perm("inventory.view_stock") is can_view


# ---------------------------------------------------------------------------
# BookForm does not touch the stock
# ---------------------------------------------------------------------------


# Generated with AI
def test_book_form_keeps_the_stock_even_if_a_stock_value_is_posted():
    book = BookFactory(stock=5)
    data = {
        "title": "Renamed",
        "author": book.author.pk,
        "price": "250.00",
        "currency": "UAH",
        "book_type": "paper",  # the select always sends one
        "description": "",
        "stock": "999",  # not a field of the form: ignored
    }

    form = BookForm(data=data, instance=Book.objects.get(pk=book.pk))
    assert form.is_valid(), form.errors
    form.save()

    book.refresh_from_db()
    assert (book.title, book.stock) == ("Renamed", 5)


# Generated with AI
def test_a_book_not_saved_yet_has_no_copies(django_assert_num_queries):
    book = Book(title="Draft")

    with django_assert_num_queries(0):  # no row can exist: no query
        assert book.stock == 0
