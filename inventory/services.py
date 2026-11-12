"""Changing the stock of books. Reading: book.stock / Book.objects.with_stock().

Orders change the stock in their own transaction with row locks
(orders.services); this module is for everything else: the book form,
the API, seed_books, the tests.
"""

from django.db.models import F

from .models import Stock, Warehouse


def set_stock(book, quantity, warehouse=None):
    """Set the number of copies of the book in a warehouse (default: the default one).

    update_or_create: the row normally exists (inventory.signals makes it
    for every new book); for a book without one it is created.
    The book object gets the new value too, so book.stock right after this
    call shows it without another query.
    """
    warehouse = warehouse or Warehouse.objects.get_default()
    Stock.objects.update_or_create(book=book, warehouse=warehouse, defaults={"quantity": quantity})
    if warehouse.is_default:
        book.stock = quantity
    return quantity


def return_to_stock(book_id, quantity, warehouse):
    """Add copies back (a cancelled order): UPDATE ... SET quantity = quantity + n.

    F("quantity") + n: the addition happens in SQL on the current value,
    so two cancellations at the same moment don't overwrite each other.
    A book without a row (someone deleted it in the admin) gets a new one.
    """
    updated = Stock.objects.filter(book_id=book_id, warehouse=warehouse).update(
        quantity=F("quantity") + quantity
    )
    if not updated:
        Stock.objects.create(book_id=book_id, warehouse=warehouse, quantity=quantity)
