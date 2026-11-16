"""Bookstore statistics built with Django ORM: filter, Q objects, annotate.

Usage:
    python manage.py book_stats
    python manage.py book_stats --max-price 200 --search Кінг --category fentezi
    python manage.py book_stats --sql          # also print generated SQL

The prices belong to the formats of a book (paper, e-book, audiobook),
each in its own currency (BookFormat.currency). "The price" of a book
here is its price "from" in UAH, like on the catalog card: the cheapest
format on sale, converted by the database with the current exchange
rates (Book.objects.with_display_price, currencies.services.price_in), so
"price <= 300" compares hryvnias with hryvnias. The value of the stock
is of the paper format: only a paper book has copies. A book without a
format on sale (or only in a currency without a rate) has no price
(NULL): price filters skip it.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Avg, Count, DecimalField, F, OuterRef, Q, Subquery, Sum

from books.models import LOW_STOCK_THRESHOLD, Book, BookFormat, Category
from currencies.models import BASE_CURRENCY
from currencies.services import current_rates, price_in


class Command(BaseCommand):
    help = "Show bookstore statistics using filter, Q objects and annotate."

    def add_arguments(self, parser):
        parser.add_argument("--max-price", type=Decimal, default=Decimal("300"))
        parser.add_argument("--search", default="Кінг")
        parser.add_argument("--category", default="fentezi", help="category slug")
        parser.add_argument("--sql", action="store_true", help="print SQL")

    def handle(self, *args, **options):
        self.show_sql = options["sql"]
        max_price = options["max_price"]
        search = options["search"]
        category_slug = options["category"]

        # The stock is not a column of the book (inventory.Stock of the
        # paper format): with_availability() adds the annotations "stock"
        # (the default warehouse) and "available" (a digital format on
        # sale, or paper with copies), and every query below uses them like
        # fields: filter(available=True), order_by("stock"), F("stock")
        # price_uah: the price "from" in UAH (the cheapest format on sale),
        # an annotation like "stock": a subquery with one CASE WHEN per
        # currency. paper_price_uah: the price of the paper format in UAH,
        # for the value of the copies in stock. One current_rates() for all
        # queries of the command.
        rates = current_rates()
        paper_price = (
            BookFormat.objects.filter(book=OuterRef("pk"), format_type=BookFormat.FormatType.PAPER)
            .annotate(uah=price_in(BASE_CURRENCY, rates=rates))
            .values("uah")[:1]
        )
        books = (
            Book.objects.with_availability()
            .with_display_price(BASE_CURRENCY, rates=rates)
            .annotate(price_uah=F("display_price"), paper_price_uah=Subquery(paper_price))
        )

        # ------------------------------------------------------------------
        # 1. filter
        # ------------------------------------------------------------------

        # field lookups: __gt (>), __lte (<=); several kwargs are joined with AND
        cheap_in_stock = books.filter(available=True, price_uah__lte=max_price).order_by(
            "price_uah"
        )
        self.section(f"filter: in stock and price <= {max_price}", cheap_in_stock)

        # __range is BETWEEN; exclude() is the opposite of filter()
        low_stock = books.filter(stock__range=(1, LOW_STOCK_THRESHOLD)).order_by("stock")
        self.section(f"filter: low stock (1..{LOW_STOCK_THRESHOLD})", low_stock)

        out_of_stock = books.filter(available=False)
        self.section("filter: out of stock", out_of_stock)

        # double underscore follows relations: Book -> categories -> slug (JOIN)
        in_category = books.filter(categories__slug=category_slug)
        self.section(f"filter across M2M: category '{category_slug}'", in_category)

        # isnull=True on M2M: books that have no category at all
        without_category = books.filter(categories__isnull=True)
        self.section("filter: books without category", without_category)

        # ------------------------------------------------------------------
        # 2. Q objects: OR (|), AND (&), NOT (~)
        # ------------------------------------------------------------------

        # OR is impossible with plain kwargs -> Q. The JOIN to categories can
        # return one book several times (one row per category), so distinct().
        search_q = (
            Q(title__icontains=search)
            | Q(author__name__icontains=search)
            | Q(categories__name__icontains=search)
        )
        found = books.filter(search_q).distinct()
        self.section(f"Q (OR): title/author/category contains '{search}'", found)

        # NOT: in stock, but not in the given category
        not_in_category = books.filter(Q(available=True) & ~Q(categories__slug=category_slug))
        self.section(f"Q (AND + NOT): in stock and not in '{category_slug}'", not_in_category)

        # mixed: (cheap OR plenty in stock) AND has description
        promo_filter = (Q(price_uah__lt=150) | Q(stock__gte=20)) & ~Q(description="")
        promo = books.filter(promo_filter).order_by("price_uah")
        self.section("Q (mixed): (price < 150 OR stock >= 20) AND has description", promo)

        # ------------------------------------------------------------------
        # 3. annotate: a computed value for every row
        # ------------------------------------------------------------------

        # aggregate per category -> GROUP BY category
        # Category -> books -> formats -> stocks: three JOINs, one row per
        # paper format per warehouse (only a paper book has stock rows).
        # filter=default_stock takes only the rows of the default
        # warehouse, so a book in several warehouses is not counted several
        # times; books_count uses distinct=True for the same reason. The
        # average price is of the paper formats for the same reason (an
        # e-book has no stock rows).
        default_stock = Q(books__formats__stocks__warehouse__is_default=True)
        categories = Category.objects.annotate(
            books_count=Count("books", distinct=True),
            # Count with filter=Q(...) counts only matching rows
            in_stock_count=Count(
                "books", filter=default_stock & Q(books__formats__stocks__quantity__gt=0)
            ),
            # The same CASE WHEN, through the relation Category -> books
            avg_price=Avg(
                price_in(
                    BASE_CURRENCY,
                    price="books__formats__price",
                    currency="books__formats__currency",
                    rates=rates,
                ),
                filter=default_stock,
            ),
            total_stock=Sum("books__formats__stocks__quantity", filter=default_stock),
        ).order_by("-books_count", "name")
        self.heading("annotate: statistics per category")
        self.print_sql(categories)
        self.stdout.write(
            f"  {'category':<20} {'books':>5} {'in stock':>8} "
            f"{'avg UAH':>10} {'total stock':>11}"
        )
        for c in categories:
            avg = f"{c.avg_price:.2f}" if c.avg_price is not None else "—"
            self.stdout.write(
                f"  {c.name:<20} {c.books_count:>5} {c.in_stock_count:>8} "
                f"{avg:>10} {c.total_stock or 0:>11}"
            )

        # F() refers to another field (or annotation) of the same row:
        # the price of the paper format in UAH * its copies
        top_value = books.annotate(
            inventory_value=F("paper_price_uah") * F("stock"),
            categories_count=Count("categories"),
            # nulls_last: books without a price in UAH (no rate) have NULL,
            # and PostgreSQL puts NULL first in a descending order
        ).order_by(F("inventory_value").desc(nulls_last=True))[:5]
        self.heading("annotate + F(): top 5 books by inventory value (paper UAH price * stock)")
        self.print_sql(top_value)
        for b in top_value:
            self.stdout.write(
                f"  {b.title:<32} {b.paper_price_uah or 0:>8} x {b.stock:<5} = "
                f"{b.inventory_value or 0:>10.2f}   categories: {b.categories_count}"
            )

        # categories having more than 2 books: filter on an annotated value
        popular = (
            Category.objects.annotate(books_count=Count("books"))
            .filter(books_count__gt=2)
            .order_by("-books_count")
        )
        self.heading("annotate + filter (HAVING): categories with > 2 books")
        self.print_sql(popular)
        for c in popular:
            self.stdout.write(f"  {c.name}: {c.books_count}")

        # ------------------------------------------------------------------
        # 4. aggregate: one summary row for the whole table
        # ------------------------------------------------------------------
        totals = books.aggregate(
            books=Count("id"),
            in_stock=Count("id", filter=Q(available=True)),
            avg_price_uah=Avg("price_uah"),
            total_stock=Sum("stock"),
            inventory_value_uah=Sum(
                F("paper_price_uah") * F("stock"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
        )
        self.heading("aggregate: whole store")
        for key, value in totals.items():
            if isinstance(value, (Decimal, float)):
                value = f"{value:.2f}"
            self.stdout.write(f"  {key:<16} {value}")

    # ----------------------------------------------------------------------
    # output helpers
    # ----------------------------------------------------------------------

    def heading(self, text):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(text))

    def print_sql(self, queryset):
        if self.show_sql:
            self.stdout.write(self.style.SQL_KEYWORD(f"  SQL: {queryset.query}"))

    def section(self, title, queryset):
        self.heading(title)
        self.print_sql(queryset)
        books = list(queryset)
        if not books:
            self.stdout.write("  (nothing found)")
        for b in books:
            # The price "from" in UAH ("—": no format on sale)
            price = f"from {b.price_uah} UAH" if b.price_uah is not None else "—"
            self.stdout.write(f"  {b.title:<32} {price:>18}   stock: {b.stock}")
