"""Step 3 of 3: the format of a line is required, one line per format.

The same book in two formats (paper and e-book) is two lines of one
order now, so the line is unique per (order, format), not per
(order, book). A separate migration from the data one (0009):
PostgreSQL refuses to ALTER a table in the same transaction that has
just updated its rows with deferred foreign key checks.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0009_fill_order_item_formats"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="orderitem",
            name="orders_orderitem_unique_book_per_order",
        ),
        migrations.AlterField(
            model_name="orderitem",
            name="format",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="order_items",
                to="books.bookformat",
                verbose_name="format",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderitem",
            constraint=models.UniqueConstraint(
                fields=("order", "format"), name="orders_orderitem_unique_format_per_order"
            ),
        ),
    ]
