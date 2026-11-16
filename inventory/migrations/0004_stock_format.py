"""Step 1 of 3: the column Stock.format, empty for now.

The stock belongs to the paper format of a book now (books.BookFormat),
not to the book: an e-book or an audiobook has no copies. The same three
steps as the move of the stock out of the book (0001 / 0002 / books 0009):
new column, copy the data (0005), remove the old column (0006).
null=True only until 0006 makes it required. Stock.book becomes optional
here too: the migrations rolled back, 0006 brings the column back empty
and 0005 fills it again, then this one makes it required as it was.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("books", "0014_create_book_formats"),
        ("inventory", "0003_move_manage_stock_permission"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stock",
            name="book",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="stocks",
                to="books.book",
                verbose_name="book",
            ),
        ),
        migrations.AddField(
            model_name="stock",
            name="format",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="stocks",
                to="books.bookformat",
                verbose_name="format",
            ),
        ),
    ]
