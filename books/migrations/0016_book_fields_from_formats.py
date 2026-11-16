"""Before the old book fields go: nothing to do forward, the copy back on reverse.

Forward: the prices, the types, the covers and the pages are already in
the formats (books.0014 made one format for every book, the site and the
API write only the formats since). The next migration (0017) removes
the old columns; nothing has to be moved first.

Reverse (migrate books 0015): 0017 has put the empty columns back, and
here every book gets the values of its main format again, the same rule
the site used while both existed: the first format on sale, else the
first one (paper, e-book, audiobook). A book without any format (made by
the API, not yet sold) gets 0 UAH "paper", so 0015 can make the price
NOT NULL again.

The constants are copied here, not imported from books.models: a
migration must keep working after the code of the models changes.
"""

from decimal import Decimal

from django.db import migrations

BASE_CURRENCY = "UAH"
PAPER = "paper"
# BookFormat.Meta.ordering: paper, e-book, audiobook
FORMAT_ORDER = {"paper": 0, "ebook": 1, "audiobook": 2}


def copy_main_format_back(apps, schema_editor):
    Book = apps.get_model("books", "Book")
    BookFormat = apps.get_model("books", "BookFormat")
    formats = {}
    for book_format in BookFormat.objects.iterator():
        formats.setdefault(book_format.book_id, []).append(book_format)
    books = list(Book.objects.all())
    for book in books:
        rows = formats.get(book.pk)
        if not rows:
            book.price, book.currency_id = Decimal("0.00"), BASE_CURRENCY
            book.book_type, book.cover_type, book.pages = PAPER, "", None
            continue
        main = min(rows, key=lambda row: (not row.is_active, FORMAT_ORDER[row.format_type]))
        book.price, book.currency_id = main.price, main.currency_id
        book.book_type, book.cover_type, book.pages = main.format_type, main.cover_type, main.pages
    Book.objects.bulk_update(
        books, ["price", "currency", "book_type", "cover_type", "pages"], batch_size=500
    )


class Migration(migrations.Migration):
    dependencies = [
        ("books", "0015_book_price_null"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, copy_main_format_back),
    ]
