"""Warehouses and the stock of paper books in them.

Before hw_31 the stock was a column of the book (Book.stock). Now a book
keeps only the information about the book itself, and the number of copies
lives here:

    Warehouse  "General" (is_default=True)
    Stock      paper format + warehouse + quantity, one row per format per warehouse

Why: the data of a book (title, price, description) changes rarely and
can be cached for a long time (stage 2), while the stock changes with
every order. In one table every purchase would make the cached book stale.

Only the PAPER format of a book (books.BookFormat) has copies: an e-book
or an audiobook is a file, always available, it has no Stock rows.

The site sells from the default warehouse only. book_format.stock,
book.stock (the copies of its paper format) and the with_stock() of both
querysets (books.models) read the quantity of that warehouse;
inventory.services changes it.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

# The warehouse made by the data migration 0002 and by get_default() on an
# empty database (tests)
DEFAULT_WAREHOUSE_NAME = "General"
DEFAULT_WAREHOUSE_SLUG = "general"


class WarehouseQuerySet(models.QuerySet):
    def get_default(self):
        """The warehouse the site sells from (is_default=True).

        get_or_create: on a database without it (made by hand, or emptied
        by a test with transaction=True) it is created again instead of
        every order failing with DoesNotExist.
        """
        warehouse, _ = self.get_or_create(
            is_default=True,
            defaults={"name": DEFAULT_WAREHOUSE_NAME, "slug": DEFAULT_WAREHOUSE_SLUG},
        )
        return warehouse


class Warehouse(models.Model):
    name = models.CharField(_("name"), max_length=100, unique=True)
    slug = models.SlugField(_("slug"), max_length=100, unique=True)
    is_default = models.BooleanField(
        _("default"),
        default=False,
        help_text=_("The site sells books from this warehouse. Only one can be the default."),
    )

    objects = WarehouseQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name = _("warehouse")
        verbose_name_plural = _("warehouses")
        constraints = [
            # Partial unique index: unique only among the rows WHERE
            # is_default = true. Any number of warehouses with False, at most
            # one with True. A second default -> IntegrityError in the
            # database, and a validation error in the admin form.
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="one_default_warehouse",
                violation_error_message=_("Another warehouse is already the default."),
            ),
        ]

    def __str__(self):
        return self.name


class Stock(models.Model):
    """How many copies of a paper book are in a warehouse."""

    format = models.ForeignKey(
        "books.BookFormat",
        verbose_name=_("format"),
        # CASCADE: the stock of a deleted format means nothing. A format
        # that is in orders can't be deleted anyway (OrderItem.format is
        # PROTECT)
        on_delete=models.CASCADE,
        related_name="stocks",  # book_format.stocks.all()
    )
    warehouse = models.ForeignKey(
        Warehouse,
        verbose_name=_("warehouse"),
        # PROTECT: a warehouse that still has stock rows can't be deleted
        on_delete=models.PROTECT,
        related_name="stocks",
    )
    # PositiveIntegerField: PostgreSQL gets CHECK (quantity >= 0) from
    # Django itself, so an UPDATE that would go below zero fails in the
    # database even if the Python check was skipped
    quantity = models.PositiveIntegerField(_("quantity"), default=0)

    class Meta:
        ordering = ["format__book__title", "warehouse__name"]
        verbose_name = _("stock")
        verbose_name_plural = _("stock")
        constraints = [
            # One row per format per warehouse: the quantity is never split
            # between two rows that would have to be added up
            models.UniqueConstraint(
                fields=["format", "warehouse"],
                name="unique_format_warehouse",
            ),
        ]

    def __str__(self):
        # str(format): "<title> — Paper", the book title without the author
        return f"{self.format} — {self.warehouse.name}: {self.quantity}"

    def clean(self):
        # A file has no copies: only the paper format is counted. Called by
        # the admin form; inventory.services never makes such a row.
        super().clean()
        if self.format_id and not self.format.is_paper:
            raise ValidationError({"format": _("Only a paper format has copies in a warehouse.")})
