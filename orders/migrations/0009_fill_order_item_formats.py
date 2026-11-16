"""Step 2 of 3: every old order line gets the format it was sold in.

Before the formats a book was sold in one way, its book_type: books 0014
made exactly that format for every book. So a line gets the format of its
book with the type of the book; if someone changed the type later, the
first format of the book (paper first); a book without any format (all
deleted by hand) gets one made from its own fields, NOT on sale.
format_type is a copy of the format's type.

Reverse: nothing to do, 0008 rolled back drops both columns.
"""

from django.db import migrations

PAPER = "paper"
AUDIOBOOK = "audiobook"
FORMAT_ORDER = {"paper": 0, "ebook": 1, "audiobook": 2}


def fill_formats(apps, schema_editor):
    Book = apps.get_model("books", "Book")
    BookFormat = apps.get_model("books", "BookFormat")
    OrderItem = apps.get_model("orders", "OrderItem")

    book_ids = set(OrderItem.objects.values_list("book_id", flat=True))
    formats = {}  # {book_id: [BookFormat, ...]}, paper first
    for book_format in BookFormat.objects.filter(book_id__in=book_ids):
        formats.setdefault(book_format.book_id, []).append(book_format)
    for book_formats in formats.values():
        book_formats.sort(key=lambda f: FORMAT_ORDER.get(f.format_type, 9))

    chosen = {}  # {book_id: BookFormat}
    for book in Book.objects.filter(pk__in=book_ids):
        book_formats = formats.get(book.pk, [])
        same_type = [f for f in book_formats if f.format_type == book.book_type]
        if same_type or book_formats:
            chosen[book.pk] = (same_type or book_formats)[0]
        else:
            chosen[book.pk] = BookFormat.objects.create(
                book_id=book.pk,
                format_type=book.book_type,
                price=book.price,
                currency_id=book.currency_id,
                cover_type=book.cover_type if book.book_type == PAPER else "",
                pages=None if book.book_type == AUDIOBOOK else book.pages,
                is_active=False,
            )

    items = list(OrderItem.objects.all())
    for item in items:
        item.format_id = chosen[item.book_id].pk
        item.format_type = chosen[item.book_id].format_type
    OrderItem.objects.bulk_update(items, ["format", "format_type"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0008_orderitem_format"),
    ]

    operations = [
        migrations.RunPython(fill_formats, migrations.RunPython.noop),
    ]
