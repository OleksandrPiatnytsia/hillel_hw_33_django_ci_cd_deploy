from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.templatetags.static import static
from django.urls import reverse
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from currencies.models import BASE_CURRENCY

LOW_STOCK_THRESHOLD = 5


class BookQuerySet(models.QuerySet):
    STOCK_IN = "in_stock"
    STOCK_LOW = "low"
    STOCK_OUT = "out"
    STOCK_STATUS_CHOICES = [
        (STOCK_IN, _("In stock")),
        # format_lazy: the number is put in when the label is shown, after
        # the translation ("Мало (≤ 5)"); an f-string would be built once,
        # in English, when the module is imported
        (STOCK_LOW, format_lazy(_("Low (≤ {threshold})"), threshold=LOW_STOCK_THRESHOLD)),
        (STOCK_OUT, _("Out of stock")),
    ]

    def with_stock(self):
        """Add the annotation "stock": copies in the default warehouse, 0 without a row.

        One subquery inside the same SELECT, for every book of the list:

            SELECT book.*, COALESCE((SELECT quantity FROM inventory_stock
                                     JOIN inventory_warehouse ...
                                     WHERE book_id = book.id AND is_default
                                     LIMIT 1), 0) AS stock
            FROM books_book

        After it book.stock is a plain value (no query per book), and
        "stock" works in filter() / order_by(): filter(stock__gt=0).
        Calling it twice is safe: the second call changes nothing.
        """
        if "stock" in self.query.annotations:
            return self
        # Imported here: inventory.models has a ForeignKey to Book, and
        # books.models is loaded first
        from inventory.models import Stock

        default_quantity = Stock.objects.filter(
            book=OuterRef("pk"), warehouse__is_default=True
        ).values("quantity")[:1]
        return self.annotate(stock=Coalesce(Subquery(default_quantity), 0))

    def with_sold(self):
        """Add the annotation "sold": copies ordered, cancelled orders not counted.

        The popularity of a book for the "Most popular" sort. A subquery
        per row, like with_stock(), not Sum("order_items__quantity"): a JOIN
        with the order items together with the JOIN of a category filter
        could count rows twice.

            COALESCE((SELECT SUM(quantity) FROM orders_orderitem
                      JOIN orders_order ...
                      WHERE book_id = book.id AND status <> 'cancelled'
                      GROUP BY book_id), 0) AS sold
        """
        if "sold" in self.query.annotations:
            return self
        # Imported here: orders.models has a ForeignKey to Book
        from orders.models import Order, OrderItem

        sold = (
            OrderItem.objects.filter(book=OuterRef("pk"))
            .exclude(order__status=Order.Status.CANCELLED)
            .values("book")  # GROUP BY book
            .annotate(total=Sum("quantity"))
            .values("total")
        )
        return self.annotate(sold=Coalesce(Subquery(sold), 0))

    def by_stock_status(self, status):
        """Filter by one of STOCK_STATUS_CHOICES; unknown/empty value -> no filter."""
        if status not in (self.STOCK_IN, self.STOCK_LOW, self.STOCK_OUT):
            return self
        books = self.with_stock()
        if status == self.STOCK_IN:
            return books.filter(stock__gt=0)
        if status == self.STOCK_LOW:
            return books.filter(stock__gt=0, stock__lte=LOW_STOCK_THRESHOLD)
        return books.filter(stock=0)


class Category(models.Model):
    name = models.CharField(_("name"), max_length=100, unique=True)
    slug = models.SlugField(_("slug"), max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("category")
        verbose_name_plural = _("categories")

    def __str__(self):
        return self.name


class Author(models.Model):
    # unique: the data migration and seed_books look authors up by name
    name = models.CharField(_("name"), max_length=255, unique=True)
    bio = models.TextField(_("biography"), blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("author")
        verbose_name_plural = _("authors")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("books:author_detail", kwargs={"pk": self.pk})


class Book(models.Model):
    title = models.CharField(_("title"), max_length=255)
    author = models.ForeignKey(
        Author,
        verbose_name=_("author"),
        on_delete=models.PROTECT,  # can't delete an author who still has books
        related_name="books",  # author.books.all()
    )
    price = models.DecimalField(
        _("price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    # The currency of the price: a book may cost 650 UAH or 20 USD. The site
    # shows the price converted to the currency of the switcher
    # (currencies.services.convert / price_in).
    # default=UAH: the existing books get UAH when the column is added (one
    # migration, no separate data migration), and a new book is in UAH
    # unless another currency is chosen. The currency "UAH" itself comes
    # from the data migration currencies.0002, which the migration of this
    # field depends on.
    currency = models.ForeignKey(
        "currencies.Currency",
        verbose_name=_("currency"),
        # PROTECT: a currency with books can't be deleted (turn it off instead)
        on_delete=models.PROTECT,
        default=BASE_CURRENCY,
        related_name="books",  # currency.books.all()
    )
    description = models.TextField(_("description"), blank=True)
    # No stock here: copies are counted in inventory.Stock (see the
    # "stock" property below and BookQuerySet.with_stock())
    # Only the path is stored in the DB; the file goes to MEDIA_ROOT/covers/<year>/<month>/
    cover = models.ImageField(_("cover"), upload_to="covers/%Y/%m/", blank=True)
    categories = models.ManyToManyField(
        Category,
        verbose_name=_("categories"),
        through="BookCategory",
        related_name="books",
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = BookQuerySet.as_manager()

    class Meta:
        ordering = ["title"]
        verbose_name = _("book")
        verbose_name_plural = _("books")
        # The stock permission is inventory.change_stock now (it was
        # books.manage_stock while the stock was a column of the book)

    def __str__(self):
        # author is a related object: use select_related("author") in lists,
        # otherwise every str(book) makes an extra query
        return f"{self.title} — {self.author.name}"

    def get_absolute_url(self):
        return reverse("books:detail", kwargs={"pk": self.pk})

    @property
    def cover_url(self):
        """Uploaded cover or the static placeholder — templates don't need if/else."""
        if self.cover:
            return self.cover.url
        return static("img/no-cover.svg")

    # ------------------------------------------------------------------
    # Stock: copies in the default warehouse (inventory.Stock)
    # ------------------------------------------------------------------

    @property
    def stock(self):
        """Copies in the default warehouse.

        Books from Book.objects.with_stock() already have the value (the
        annotation is stored through the setter below): no query. Any other
        book object reads it with one query, then keeps it.
        In lists always use with_stock(): otherwise one query per book.
        """
        if "_stock" not in self.__dict__:
            if self.pk is None:
                self._stock = 0
            else:
                quantity = (
                    self.stocks.filter(warehouse__is_default=True)
                    .values_list("quantity", flat=True)
                    .first()
                )
                self._stock = quantity or 0
        return self._stock

    @stock.setter
    def stock(self, value):
        # Only the value of this object: used by with_stock() (Django sets
        # annotations with setattr) and by inventory.services.set_stock().
        # It does NOT save anything: the stock is changed through
        # inventory.services, not book.stock = 5; book.save().
        self._stock = value

    def refresh_from_db(self, *args, **kwargs):
        # The stock may have changed too: read it again on the next access
        self.__dict__.pop("_stock", None)
        super().refresh_from_db(*args, **kwargs)

    @property
    def is_low_stock(self):
        return 0 < self.stock <= LOW_STOCK_THRESHOLD


class BookCategory(models.Model):
    """Link between Book and Category.

    An explicit through model lets us protect categories from deletion
    while they still contain books (plain M2M has no on_delete).
    """

    book = models.ForeignKey(Book, on_delete=models.CASCADE, verbose_name=_("book"))
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name=_("category"))

    class Meta:
        verbose_name = _("book category")
        verbose_name_plural = _("book categories")
        constraints = [
            models.UniqueConstraint(
                fields=["book", "category"],
                name="unique_book_category",
            ),
        ]

    def __str__(self):
        return f"{self.book.title} → {self.category.name}"
