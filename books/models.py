from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, OuterRef, Prefetch, Subquery, Sum
from django.db.models.functions import Coalesce
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from currencies.models import BASE_CURRENCY

LOW_STOCK_THRESHOLD = 5

# The first printed books (Gutenberg's Bible, about 1455): an earlier
# "publication year" is a typo
FIRST_PUBLICATION_YEAR = 1450


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

    def with_active_formats(self):
        """Load the formats on sale of every book in one extra query.

        book.active_formats then reads this list, not the database: a
        catalog page of 24 cards needs 1 query for their formats, not 24.
        """
        # Imported here: BookFormat is defined below Book
        return self.prefetch_related(
            Prefetch(
                "formats",
                queryset=BookFormat.objects.filter(is_active=True),
                to_attr="prefetched_active_formats",
            )
        )

    def with_display_price(self, currency_code, rates=None):
        """Add "display_price": the cheapest format on sale, in currency_code.

        The formats have prices in different currencies (paper 450 UAH,
        e-book 5 USD), so the cheapest is found by the price converted by
        the database (currencies.services.price_in), one subquery per book:

            (SELECT <price in USD> FROM books_bookformat
             WHERE book_id = book.id AND is_active
             ORDER BY 1 ASC NULLS LAST LIMIT 1) AS display_price

        The price "from" of the card, the "Price from / to" filter, the sort
        by price and the price slider all use it. NULL: no format on sale
        (or none with an exchange rate): such a book goes last in the sort
        and is never in a price range.
        """
        # Imported here: currencies.services imports nothing from books,
        # but keeps the models module free of the services layer
        from currencies.services import price_in

        cheapest = (
            BookFormat.objects.filter(book=OuterRef("pk"), is_active=True)
            .annotate(converted=price_in(currency_code, rates=rates))
            .order_by(F("converted").asc(nulls_last=True))
            .values("converted")[:1]
        )
        return self.annotate(display_price=Subquery(cheapest))

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


def validate_not_future_year(value):
    """The publication year can't be later than this year.

    A function, not MaxValueValidator(2026): the number would be written
    into the migration once and refuse every new book from 2027 on. The
    migration keeps only the path to this function, the year is taken at
    the moment of the check.
    """
    if value > timezone.now().year:
        raise ValidationError(
            _("The publication year can't be later than %(year)s."),
            code="future_year",
            params={"year": timezone.now().year},
        )


class Publisher(models.Model):
    """A publishing house: "Видавництво Старого Лева", "Ранок", ...

    A model, not a text field of the book: one spelling for all its books
    (no "Ранок" next to "ВД Ранок"), a list to choose from in the form and
    in the catalog filter. The main Ukrainian publishers are added by the
    data migration books.0012.
    """

    # unique: the data migration looks publishers up by name
    name = models.CharField(_("name"), max_length=255, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("publisher")
        verbose_name_plural = _("publishers")

    def __str__(self):
        return self.name


class Book(models.Model):
    class BookType(models.TextChoices):
        # The value is stored in the database (and used in the URL of the
        # filter: ?book_type=ebook), the label is shown and translated
        PAPER = "paper", _("Paper book")
        EBOOK = "ebook", _("E-book")
        AUDIOBOOK = "audiobook", _("Audiobook")

    class CoverType(models.TextChoices):
        HARD = "hard", _("Hardcover")
        SOFT = "soft", _("Paperback")
        DUST_JACKET = "dust_jacket", _("Dust jacket")

    class Language(models.TextChoices):
        # ISO 639-1 codes, like the languages of the site (settings.LANGUAGES)
        UKRAINIAN = "uk", _("Ukrainian")
        ENGLISH = "en", _("English")
        POLISH = "pl", _("Polish")
        GERMAN = "de", _("German")
        FRENCH = "fr", _("French")
        SPANISH = "es", _("Spanish")

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

    # ---- Details of the edition (the "Details" block of the book page and
    # the filters of the catalog). All may be empty: the books added before
    # these fields have none of them, except the type ("paper").
    publisher = models.ForeignKey(
        Publisher,
        verbose_name=_("publisher"),
        # PROTECT: a publisher with books can't be deleted
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="books",  # publisher.books.all()
    )
    # All types are sold the same way for now (stock in the warehouse,
    # delivery): e-books without stock are a later task (README "Плани")
    book_type = models.CharField(
        _("book type"), max_length=10, choices=BookType.choices, default=BookType.PAPER
    )
    # Only for paper books (see clean()); empty = not known
    cover_type = models.CharField(_("cover"), max_length=11, choices=CoverType.choices, blank=True)
    language = models.CharField(_("language"), max_length=2, choices=Language.choices, blank=True)
    publication_year = models.PositiveSmallIntegerField(
        _("publication year"),
        null=True,
        blank=True,
        validators=[MinValueValidator(FIRST_PUBLICATION_YEAR), validate_not_future_year],
    )
    # Shown on the book page, not a filter of the catalog
    pages = models.PositiveSmallIntegerField(
        _("pages"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10000)],
    )

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

    def clean(self):
        # A cover is a part of a printed book: an e-book or an audiobook
        # with "Hardcover" is a mistake of the form. Called by the forms
        # (site and admin), not by save().
        super().clean()
        if self.cover_type and self.book_type != self.BookType.PAPER:
            raise ValidationError({"cover_type": _("Only a paper book has a cover type.")})

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
        # The stock and the formats may have changed too: read them again
        # on the next access
        self.__dict__.pop("_stock", None)
        self.__dict__.pop("prefetched_active_formats", None)
        super().refresh_from_db(*args, **kwargs)

    @property
    def is_low_stock(self):
        return 0 < self.stock <= LOW_STOCK_THRESHOLD

    # ------------------------------------------------------------------
    # Formats (BookFormat): paper, e-book, audiobook
    # ------------------------------------------------------------------

    @property
    def active_formats(self):
        """The formats on sale, paper first: [BookFormat, ...].

        From Book.objects.with_active_formats() (and the cached book of the
        book page): no query. Any other book reads them with one query, then
        keeps the list.
        """
        if "prefetched_active_formats" not in self.__dict__:
            if self.pk is None:
                self.prefetched_active_formats = []
            else:
                self.prefetched_active_formats = list(self.formats.filter(is_active=True))
        return self.prefetched_active_formats

    def format_of_type(self, format_type):
        """The format of this type on sale, or None: book.format_of_type("paper")."""
        return next((f for f in self.active_formats if f.format_type == format_type), None)

    @property
    def paper_format(self):
        """The paper format on sale, or None: its cover is the cover of the book."""
        return self.format_of_type(BookFormat.FormatType.PAPER)

    @property
    def pages_count(self):
        """The pages of the paper format, else of the e-book; None if not known."""
        return next((f.pages for f in self.active_formats if f.pages), None)


class BookFormat(models.Model):
    """One way to buy a book: paper, e-book or audiobook, each with its own price.

    The same book (title, author, description, publisher, language, year,
    categories, cover image) is sold in up to three formats:

        «Тигролови»  paper      450 UAH, hard cover, 320 pages
                     ebook      199 UAH
                     audiobook  249 UAH

    The format is chosen on the book page before the cart and can be
    changed in the cart. The price, the cover type and the pages belong to
    the format: an e-book has no cover, a paper book costs more.

    One format of a type per book (unique book + format_type). is_active:
    the format is not sold now (sold out for good, rights expired), but
    stays for the old orders.
    """

    class FormatType(models.TextChoices):
        # The value is stored in the database and in the URL of the filter
        # (?book_type=ebook); the label is shown on the format tiles.
        # pgettext: the context "book format" gives these labels their own
        # translations, short for a tile («Електронна»), while the same
        # English "E-book" of Book.BookType stays «Електронна книга»
        PAPER = "paper", pgettext_lazy("book format", "Paper")
        EBOOK = "ebook", pgettext_lazy("book format", "E-book")
        AUDIOBOOK = "audiobook", pgettext_lazy("book format", "Audiobook")

    book = models.ForeignKey(
        Book,
        verbose_name=_("book"),
        # CASCADE: the formats of a deleted book mean nothing. A book with
        # orders can't be deleted anyway (OrderItem.book is PROTECT)
        on_delete=models.CASCADE,
        related_name="formats",  # book.formats.all()
    )
    format_type = models.CharField(_("format"), max_length=10, choices=FormatType.choices)
    price = models.DecimalField(
        _("price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    # The currency of the price, like Book.currency: a paper book in UAH,
    # its e-book in USD is allowed
    currency = models.ForeignKey(
        "currencies.Currency",
        verbose_name=_("currency"),
        on_delete=models.PROTECT,
        default=BASE_CURRENCY,
        related_name="book_formats",  # currency.book_formats.all()
    )
    # Only for the paper format (see clean()); empty = not known
    cover_type = models.CharField(
        _("cover"), max_length=11, choices=Book.CoverType.choices, blank=True
    )
    # Paper and e-book; an audiobook has hours, not pages (not stored)
    pages = models.PositiveSmallIntegerField(
        _("pages"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10000)],
    )
    is_active = models.BooleanField(
        _("on sale"),
        default=True,
        help_text=_("Turn off to stop selling this format; old orders keep it."),
    )

    class Meta:
        # Paper first, then e-book, then audiobook: the order of the tiles
        # on the book page. Alphabetical order of the values would put the
        # audiobook first. "book_id", not "book": "book" would sort by the
        # ordering of Book (its title) through a JOIN.
        ordering = [
            "book_id",
            models.Case(
                models.When(format_type="paper", then=0),
                models.When(format_type="ebook", then=1),
                default=2,
            ),
        ]
        verbose_name = _("book format")
        verbose_name_plural = _("book formats")
        constraints = [
            # One paper format per book, one e-book, one audiobook: two
            # "paper" rows would have two prices for the same thing
            models.UniqueConstraint(
                fields=["book", "format_type"],
                name="unique_book_format_type",
                violation_error_message=_("The book already has this format."),
            ),
        ]

    def __str__(self):
        # book.title, not str(book): str(book) also needs the author
        return f"{self.book.title} — {self.get_format_type_display()}"

    def clean(self):
        # The same rule as Book.clean(): a cover is a part of a printed book
        super().clean()
        errors = {}
        if self.cover_type and self.format_type != self.FormatType.PAPER:
            errors["cover_type"] = _("Only a paper book has a cover type.")
        if self.pages and self.format_type == self.FormatType.AUDIOBOOK:
            errors["pages"] = _("An audiobook has no pages.")
        if errors:
            raise ValidationError(errors)


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
