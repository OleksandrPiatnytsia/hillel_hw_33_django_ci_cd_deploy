"""The data migrations of the formats, on a real database.

    books 0014      one format for every book, from the old book fields
    inventory 0005  every stock row goes from its book to the paper format
    orders 0009     every old order line gets the format it was sold in
    books 0015-17   the old book fields go; back: the main format fills them

The database is rolled back to the state before them (books 0014 with
the old fields, inventory 0004, orders 0008), filled with the historical
models, then migrated forward again: exactly what happens on Railway with
the data of the release before. transaction=True: migrations can't run inside the test's own
transaction. serialized_rollback=True: the data of the data migrations
(currencies, groups, the warehouse) is loaded again first, an earlier
test with transaction=True has emptied the tables. The finally block
always brings the schema back to the latest state, the other tests need it.
"""

import importlib
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from ..factories import UserFactory

# books 0014 too: the old book fields are there, and the historical models
# of these targets have them (the executor moves only the named apps)
BOOKS_WITH_OLD_FIELDS = ("books", "0014_create_book_formats")
BEFORE = [
    BOOKS_WITH_OLD_FIELDS,
    ("inventory", "0004_stock_format"),
    ("orders", "0008_orderitem_format"),
]

# A module name that starts with a digit can't be imported with "import"
create_book_formats = importlib.import_module("books.migrations.0014_create_book_formats")


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


# Generated with AI
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_the_first_formats_are_made_from_the_old_fields_of_the_book():
    """books 0014: the type, the price, the currency, the cover and the pages."""
    try:
        apps = _migrate([BOOKS_WITH_OLD_FIELDS])
        Author = apps.get_model("books", "Author")
        Book = apps.get_model("books", "Book")
        author = Author.objects.create(name="Іван Багряний")
        paper = Book.objects.create(
            title="Тигролови",
            author=author,
            price=Decimal("450.00"),
            currency_id="EUR",
            cover_type="hard",
            pages=320,
        )
        # Saved past the form: Book.clean() refused a cover of a non-paper book
        audiobook = Book.objects.create(
            title="Сад Гетсиманський",
            author=author,
            price=Decimal("249.00"),
            book_type="audiobook",
            cover_type="soft",
            pages=10,
        )

        create_book_formats.create_formats(apps, None)

        BookFormat = apps.get_model("books", "BookFormat")
        made = {f.book_id: f for f in BookFormat.objects.filter(book__author=author)}
        assert (made[paper.pk].format_type, made[paper.pk].price, made[paper.pk].currency_id) == (
            "paper",
            Decimal("450.00"),
            "EUR",
        )
        assert (made[paper.pk].cover_type, made[paper.pk].pages) == ("hard", 320)
        # An audiobook keeps its price, but no cover and no pages
        assert made[audiobook.pk].format_type == "audiobook"
        assert (made[audiobook.pk].cover_type, made[audiobook.pk].pages) == ("", None)
    finally:
        _migrate(_latest())


# Generated with AI
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_the_old_book_fields_go_and_come_back_from_the_main_format():
    """books 0015-0017 forward: only the columns go; back: the main format fills them."""
    try:
        apps = _migrate([BOOKS_WITH_OLD_FIELDS])
        Author = apps.get_model("books", "Author")
        Book = apps.get_model("books", "Book")
        BookFormat = apps.get_model("books", "BookFormat")
        author = Author.objects.create(name="Ліна Костенко")
        # The paper book is not on sale: the main format is the e-book
        both = Book.objects.create(title="Маруся Чурай", author=author, price=Decimal("1"))
        BookFormat.objects.create(book=both, format_type="paper", price=300, is_active=False)
        BookFormat.objects.create(
            book=both, format_type="ebook", price=Decimal("5.00"), currency_id="USD", pages=200
        )
        # A book made by the API without a format yet
        bare = Book.objects.create(title="Берестечко", author=author, price=Decimal("1"))

        apps = _migrate(_latest())
        Book = apps.get_model("books", "Book")
        assert not hasattr(Book(), "price")
        # The formats are untouched
        assert apps.get_model("books", "BookFormat").objects.filter(book_id=both.pk).count() == 2

        apps = _migrate([BOOKS_WITH_OLD_FIELDS])
        Book = apps.get_model("books", "Book")
        fields = ("price", "currency_id", "book_type", "cover_type", "pages")
        assert Book.objects.filter(pk=both.pk).values_list(*fields).get() == (
            Decimal("5.00"),
            "USD",
            "ebook",
            "",
            200,
        )
        assert Book.objects.filter(pk=bare.pk).values_list(*fields).get() == (
            Decimal("0.00"),
            "UAH",
            "paper",
            "",
            None,
        )
    finally:
        _migrate(_latest())
