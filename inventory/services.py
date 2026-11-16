"""Changing the stock of paper books. Reading: book_format.stock / book.stock.

Orders change the stock in their own transaction with row locks
(orders.services); this module is for everything else: the admin, the
API, seed_books, the tests.
"""

from django.db.models import F

from .models import Stock, Warehouse


def paper_format_of(book):
    """The paper format of a book (on sale or not), or None.

    The stock of a book is the stock of its paper format: an e-book or an
    audiobook has no copies.
    """
    # Imported here: books.models imports inventory.models lazily too
    from books.models import BookFormat

    return book.formats.filter(format_type=BookFormat.FormatType.PAPER).first()


def set_stock(target, quantity, warehouse=None):
    """Set the number of copies in a warehouse (default: the default one).

    target: a paper BookFormat, or a Book (then its paper format).
    A book without a paper format, an e-book or an audiobook -> ValueError:
    a file has no copies.

    update_or_create: the row normally exists (inventory.signals makes it
    for every new paper format); for a format without one it is created.
    The object gets the new value too (format.stock, and book.stock when a
    book was given), so it shows it right after this call without a query.
    """
    # Imported here, like above
    from books.models import Book

    book = target if isinstance(target, Book) else None
    book_format = paper_format_of(target) if book is not None else target
    if book_format is None or not book_format.is_paper:
        raise ValueError(f"{target!r} has no paper format: only paper books have copies")

    warehouse = warehouse or Warehouse.objects.get_default()
    Stock.objects.update_or_create(
        format=book_format, warehouse=warehouse, defaults={"quantity": quantity}
    )
    if warehouse.is_default:
        book_format.stock = quantity
        if book is not None:
            book.stock = quantity
    return quantity


def return_to_stock(format_id, quantity, warehouse):
    """Add copies back (a cancelled order): UPDATE ... SET quantity = quantity + n.

    F("quantity") + n: the addition happens in SQL on the current value,
    so two cancellations at the same moment don't overwrite each other.
    A format without a row (someone deleted it in the admin) gets a new one.
    """
    updated = Stock.objects.filter(format_id=format_id, warehouse=warehouse).update(
        quantity=F("quantity") + quantity
    )
    if not updated:
        Stock.objects.create(format_id=format_id, warehouse=warehouse, quantity=quantity)
