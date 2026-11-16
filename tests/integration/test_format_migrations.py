"""The data migrations of stage 3 of the formats, on a real database.

    inventory 0005  every stock row goes from its book to the paper format
    orders 0009     every old order line gets the format it was sold in

The database is rolled back to the state before them (inventory 0004,
orders 0008), filled with the historical models, then migrated forward
again: exactly what happens on Railway with the data of the release
before. transaction=True: migrations can't run inside the test's own
transaction. serialized_rollback=True: the data of the data migrations
(currencies, groups, the warehouse) is loaded again first, an earlier
test with transaction=True has emptied the tables. The finally block
always brings the schema back to the latest state, the other tests need it.
"""

from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from ..factories import UserFactory

BEFORE = [("inventory", "0004_stock_format"), ("orders", "0008_orderitem_format")]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


def _latest():
    return MigrationExecutor(connection).loader.graph.leaf_nodes()


# Generated with AI
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_stock_moves_to_the_paper_format_and_order_lines_get_their_formats():
    try:
        apps = _migrate(BEFORE)
        Author = apps.get_model("books", "Author")
        Book = apps.get_model("books", "Book")
        BookFormat = apps.get_model("books", "BookFormat")
        Stock = apps.get_model("inventory", "Stock")
        Warehouse = apps.get_model("inventory", "Warehouse")
        Order = apps.get_model("orders", "Order")
        OrderItem = apps.get_model("orders", "OrderItem")

        author = Author.objects.create(name="Іван Багряний")
        paper_book = Book.objects.create(title="Тигролови", author=author, price=Decimal("450"))
        ebook_book = Book.objects.create(
            title="Сад Гетсиманський", author=author, price=Decimal("199"), book_type="ebook"
        )
        # As books 0014 made them: one format of the book's type
        paper = BookFormat.objects.create(book=paper_book, format_type="paper", price=450)
        ebook = BookFormat.objects.create(book=ebook_book, format_type="ebook", price=199)
        # A book that lost its formats: its old order line still needs one
        lost = Book.objects.create(title="Без формату", author=author, price=Decimal("100"))

        warehouse, _ = Warehouse.objects.get_or_create(
            is_default=True, defaults={"name": "General", "slug": "general"}
        )
        Stock.objects.create(book=paper_book, warehouse=warehouse, quantity=7)
        Stock.objects.create(book=ebook_book, warehouse=warehouse, quantity=3)

        # The users table is not rolled back: the current model (the historical
        # state of these targets knows only the first migrations of users)
        user = UserFactory()
        order = Order.objects.create(user_id=user.pk, full_name="Ann", phone="+380", address="Kyiv")
        for book in (paper_book, ebook_book, lost):
            OrderItem.objects.create(
                order=order,
                book=book,
                title=book.title,
                price=book.price,
                original_price=book.price,
                original_currency_id="UAH",
                exchange_rate=1,
                quantity=1,
            )

        apps = _migrate(_latest())
        Stock = apps.get_model("inventory", "Stock")
        OrderItem = apps.get_model("orders", "OrderItem")
        BookFormat = apps.get_model("books", "BookFormat")

        # The copies of the paper book stay; the e-book's row is gone
        assert list(Stock.objects.values_list("format_id", "quantity")) == [(paper.pk, 7)]
        lines = {
            item.book_id: (item.format_id, item.format_type) for item in OrderItem.objects.all()
        }
        assert lines[paper_book.pk] == (paper.pk, "paper")
        assert lines[ebook_book.pk] == (ebook.pk, "ebook")
        made = BookFormat.objects.get(book_id=lost.pk)
        assert lines[lost.pk] == (made.pk, "paper")
        assert made.is_active is False  # made only for the old order, not sold

        # Rolled back: the rows belong to the books again, the e-book's row
        # comes back as 0 (every book had a row before)
        apps = _migrate(BEFORE)
        Stock = apps.get_model("inventory", "Stock")
        assert dict(Stock.objects.values_list("book_id", "quantity")) == {
            paper_book.pk: 7,
            ebook_book.pk: 0,
            lost.pk: 0,
        }
    finally:
        _migrate(_latest())
