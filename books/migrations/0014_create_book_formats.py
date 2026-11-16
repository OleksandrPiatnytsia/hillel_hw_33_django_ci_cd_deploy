"""One format for every existing book, from the book's own fields.

    Book.book_type   -> BookFormat.format_type
    Book.price       -> BookFormat.price
    Book.currency    -> BookFormat.currency
    Book.cover_type  -> BookFormat.cover_type   (only for paper, see below)
    Book.pages       -> BookFormat.pages        (not for an audiobook)

The book fields stay for now: the site still reads them until the last
stage of the formats moves everything to BookFormat and removes them.

A cover type of a non-paper book or the pages of an audiobook would break
BookFormat.clean(); Book.clean() had the same cover rule, but a value
saved past the form (shell, loaddata) is not checked, so they are dropped
here instead of copied.

Reverse: deletes the formats. The book fields were never changed, so
nothing has to be copied back.
"""

from django.db import migrations

PAPER = "paper"
AUDIOBOOK = "audiobook"


def create_formats(apps, schema_editor):
    Book = apps.get_model("books", "Book")
    BookFormat = apps.get_model("books", "BookFormat")
    # exclude(): a book that already has a format of its type (the
    # migration applied, rolled back with --fake, applied again) is skipped
    # instead of breaking the unique (book, format_type) constraint
    formats = [
        BookFormat(
            book_id=book.pk,
            format_type=book.book_type,
            price=book.price,
            currency_id=book.currency_id,
            cover_type=book.cover_type if book.book_type == PAPER else "",
            pages=None if book.book_type == AUDIOBOOK else book.pages,
            is_active=True,
        )
        for book in Book.objects.exclude(formats__isnull=False).iterator()
    ]
    BookFormat.objects.bulk_create(formats)


def delete_formats(apps, schema_editor):
    apps.get_model("books", "BookFormat").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("books", "0013_bookformat"),
    ]

    operations = [
        migrations.RunPython(create_formats, delete_formats),
    ]
