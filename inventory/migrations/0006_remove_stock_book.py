"""Step 3 of 3: Stock.book is gone, Stock.format is required.

One row per format per warehouse instead of one per book per warehouse.
A separate migration from the data one (0005): PostgreSQL refuses to
ALTER a table in the same transaction that has just updated its rows
with deferred foreign key checks ("pending trigger events").
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0005_move_stock_to_paper_format"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="stock",
            name="unique_book_warehouse",
        ),
        migrations.AlterModelOptions(
            name="stock",
            options={
                "ordering": ["format__book__title", "warehouse__name"],
                "verbose_name": "stock",
                "verbose_name_plural": "stock",
            },
        ),
        migrations.RemoveField(
            model_name="stock",
            name="book",
        ),
        migrations.AlterField(
            model_name="stock",
            name="format",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="stocks",
                to="books.bookformat",
                verbose_name="format",
            ),
        ),
        migrations.AddConstraint(
            model_name="stock",
            constraint=models.UniqueConstraint(
                fields=("format", "warehouse"), name="unique_format_warehouse"
            ),
        ),
    ]
