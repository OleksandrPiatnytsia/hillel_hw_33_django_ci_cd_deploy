"""BookFormat: one book in up to three formats (paper, e-book, audiobook), each with its own price.

The formats of the existing books come from the next migration (0014).
"""

import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0012_create_publishers"),
        ("currencies", "0002_create_currencies"),
    ]

    operations = [
        migrations.CreateModel(
            name="BookFormat",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "format_type",
                    models.CharField(
                        choices=[
                            ("paper", "Paper"),
                            ("ebook", "E-book"),
                            ("audiobook", "Audiobook"),
                        ],
                        max_length=10,
                        verbose_name="format",
                    ),
                ),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                        verbose_name="price",
                    ),
                ),
                (
                    "cover_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("hard", "Hardcover"),
                            ("soft", "Paperback"),
                            ("dust_jacket", "Dust jacket"),
                        ],
                        max_length=11,
                        verbose_name="cover",
                    ),
                ),
                (
                    "pages",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(10000),
                        ],
                        verbose_name="pages",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Turn off to stop selling this format; old orders keep it.",
                        verbose_name="on sale",
                    ),
                ),
                (
                    "book",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="formats",
                        to="books.book",
                        verbose_name="book",
                    ),
                ),
                (
                    "currency",
                    models.ForeignKey(
                        default="UAH",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="book_formats",
                        to="currencies.currency",
                        verbose_name="currency",
                    ),
                ),
            ],
            options={
                "verbose_name": "book format",
                "verbose_name_plural": "book formats",
                "ordering": [
                    "book_id",
                    models.Case(
                        models.When(format_type="paper", then=0),
                        models.When(format_type="ebook", then=1),
                        default=2,
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("book", "format_type"),
                        name="unique_book_format_type",
                        violation_error_message="The book already has this format.",
                    )
                ],
            },
        ),
    ]
