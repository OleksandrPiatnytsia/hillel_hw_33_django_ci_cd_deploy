"""Step 1 of 3: OrderItem.format and OrderItem.format_type, empty for now.

A line of an order is a FORMAT of a book now (paper, e-book, audiobook),
each with its own price. 0009 gives the old lines the format they were
sold in, 0010 makes the format required and the line unique per format.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("books", "0014_create_book_formats"),
        ("orders", "0007_alter_orderitem_exchange_rate_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="format",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="order_items",
                to="books.bookformat",
                verbose_name="format",
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="format_type",
            field=models.CharField(
                choices=[("paper", "Paper"), ("ebook", "E-book"), ("audiobook", "Audiobook")],
                # Only for the rows that exist now; 0009 writes the real value
                default="paper",
                max_length=10,
                verbose_name="format type",
            ),
            preserve_default=False,
        ),
    ]
