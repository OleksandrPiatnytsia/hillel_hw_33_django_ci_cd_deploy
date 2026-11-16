"""Step 2 of 3: every stock row goes from its book to the book's paper format.

    Stock(book=«Кобзар», General, 7) -> Stock(format=«Кобзар» paper, General, 7)

A book without a paper format (an e-book or an audiobook, made so by
books 0014 from its book_type) has no copies: its rows are deleted.
A file is always available, so nothing is lost for the customers.

Reverse: the format of a row gives its book back. The deleted rows of the
e-books come back only as 0 (inventory.signals made such rows for every
book): the number in them meant nothing.
"""

from django.db import migrations

PAPER = "paper"


def move_to_paper_format(apps, schema_editor):
    BookFormat = apps.get_model("books", "BookFormat")
    Stock = apps.get_model("inventory", "Stock")

    # {book_id: id of its paper format}: one query, not one per row
    paper = dict(BookFormat.objects.filter(format_type=PAPER).values_list("book_id", "pk"))
    rows = list(Stock.objects.all())
    for row in rows:
        row.format_id = paper.get(row.book_id)
    Stock.objects.bulk_update([row for row in rows if row.format_id], ["format"])
    Stock.objects.filter(format__isnull=True).delete()


def move_back_to_book(apps, schema_editor):
    Book = apps.get_model("books", "Book")
    Stock = apps.get_model("inventory", "Stock")
    Warehouse = apps.get_model("inventory", "Warehouse")

    rows = list(Stock.objects.select_related("format"))
    for row in rows:
        row.book_id = row.format.book_id
    Stock.objects.bulk_update(rows, ["book"])
    # Every book had a row in the default warehouse before: the e-books too
    warehouse = Warehouse.objects.filter(is_default=True).first()
    if warehouse is not None:
        Stock.objects.bulk_create(
            Stock(book_id=book_id, warehouse=warehouse, quantity=0)
            for book_id in Book.objects.exclude(stocks__warehouse=warehouse).values_list(
                "pk", flat=True
            )
        )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0004_stock_format"),
    ]

    operations = [
        migrations.RunPython(move_to_paper_format, move_back_to_book),
    ]
