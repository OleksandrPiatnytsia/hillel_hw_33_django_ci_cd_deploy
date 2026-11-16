from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from inventory.models import Stock

from .models import Author, Book, BookCategory, BookFormat, BookQuerySet, Category, Publisher

# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------


class BaseBookCategoryInline(admin.TabularInline):
    model = BookCategory

    def get_queryset(self, request):
        # Row titles use BookCategory.__str__ (book + category names):
        # join them in one query instead of 2 extra queries per row
        return super().get_queryset(request).select_related("book", "category")


class BookCategoryInline(BaseBookCategoryInline):
    """Categories of a book, shown on the Book page."""

    extra = 1
    autocomplete_fields = ["category"]
    verbose_name = _("category")
    verbose_name_plural = _("categories")


class CategoryBookInline(BaseBookCategoryInline):
    """Books of a category, shown on the Category page."""

    extra = 0
    autocomplete_fields = ["book"]
    verbose_name = _("book")
    verbose_name_plural = _("books")


class StockInline(admin.TabularInline):
    """Copies of a paper book per warehouse, on the page of its paper format.

    Editable only with inventory.change_stock (group "Managers"): Django
    shows the rows read-only for users with only view_stock (Editors).
    An e-book or an audiobook has no copies: no rows (see
    BookFormatAdmin.get_inlines).
    """

    model = Stock
    extra = 0
    fields = ["warehouse", "quantity"]
    verbose_name = _("stock")
    verbose_name_plural = _("stock")

    def has_add_permission(self, request, obj=None):
        # A new format (obj is None): no rows here. Its row in the default
        # warehouse is made by inventory.signals right after the format is
        # saved; a row from this form for the same warehouse would then
        # break the unique (format, warehouse) constraint.
        if obj is None:
            return False
        return super().has_add_permission(request, obj)


class BookFormatInline(admin.TabularInline):
    """Formats of the book (paper, e-book, audiobook) with their prices, on the Book page.

    One row per format. BookFormat.clean() refuses a cover for a non-paper
    format and pages for an audiobook; the unique (book, format_type)
    constraint refuses a second row of the same format.
    Rights: books.add/change/delete_bookformat (Editors and Managers).
    The copies of the paper book are on the page of the format: the link
    "Change" of its row (show_change_link) opens it.
    """

    model = BookFormat
    fields = ["format_type", "price", "currency", "cover_type", "pages", "is_active"]
    verbose_name = _("format")
    verbose_name_plural = _("formats")
    show_change_link = True

    def get_extra(self, request, obj=None, **kwargs):
        # A new book (obj is None): one empty row to fill; an existing book:
        # only its formats, "Add another" for one more
        return 1 if obj is None else 0


# ---------------------------------------------------------------------------
# Custom filters
# ---------------------------------------------------------------------------


class StockStatusFilter(admin.SimpleListFilter):
    title = _("stock status")
    parameter_name = "stock_status"

    def lookups(self, request, model_admin):
        return BookQuerySet.STOCK_STATUS_CHOICES

    def queryset(self, request, queryset):
        return queryset.by_stock_status(self.value())


# ---------------------------------------------------------------------------
# Model admins
# ---------------------------------------------------------------------------


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "books_count"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}
    # Explicit ordering: Meta.ordering is ignored for annotated (GROUP BY) queries
    ordering = ["name"]
    inlines = [CategoryBookInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(books_count=Count("books"))

    @admin.display(description=_("books"), ordering="books_count")
    def books_count(self, obj):
        return obj.books_count


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ["name", "books_count"]
    # search_fields is also required for autocomplete_fields = ["author"] in BookAdmin (stage 4)
    search_fields = ["name"]
    # Explicit ordering: Meta.ordering is ignored for annotated (GROUP BY) queries
    ordering = ["name"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(books_count=Count("books"))

    @admin.display(description=_("books"), ordering="books_count")
    def books_count(self, obj):
        return obj.books_count


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    list_display = ["name", "books_count"]
    # search_fields is also required for autocomplete_fields = ["publisher"] in BookAdmin
    search_fields = ["name"]
    # Explicit ordering: Meta.ordering is ignored for annotated (GROUP BY) queries
    ordering = ["name"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(books_count=Count("books"))

    @admin.display(description=_("books"), ordering="books_count")
    def books_count(self, obj):
        return obj.books_count


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = [
        "cover_thumbnail",
        "title",
        "author",
        "price",
        "currency",
        "stock",
        "is_available",
        "category_list",
        "created_at",
    ]
    list_display_links = ["title"]
    # No "stock" here: it is a value of inventory.Stock, not a column of
    # the book; quantities are edited in the Stock list or on the book page
    list_editable = ["price"]
    list_filter = [
        StockStatusFilter,
        "currency",
        "categories",
        "book_type",
        "language",
        "publisher",
        "created_at",
    ]
    search_fields = [
        "title",
        "author__name",
        "description",
        "categories__name",
        "publisher__name",
    ]
    date_hierarchy = "created_at"
    # Search-as-you-type instead of a <select> with every author
    # (needs search_fields in AuthorAdmin and PublisherAdmin)
    autocomplete_fields = ["author", "publisher"]
    readonly_fields = ["cover_preview", "created_at", "updated_at"]
    inlines = [BookFormatInline, BookCategoryInline]
    fieldsets = [
        (None, {"fields": ["title", "author", "description"]}),
        # The edition; tuples = fields on one line
        (
            _("Details"),
            {
                "fields": [
                    "publisher",
                    ("book_type", "cover_type"),
                    ("language", "publication_year", "pages"),
                ]
            },
        ),
        (_("Cover"), {"fields": ["cover_preview", "cover"]}),
        # A tuple = fields on one line: the price and its currency side by side
        (_("Sales"), {"fields": [("price", "currency")]}),
        (
            _("Timestamps"),
            {"fields": ["created_at", "updated_at"], "classes": ["collapse"]},
        ),
    ]

    def get_queryset(self, request):
        # Author and currency via JOIN, categories in one extra query — not
        # a query per row
        return (
            super()
            .get_queryset(request)
            .select_related("author", "currency")
            .prefetch_related("categories")
            # "stock" (of the paper format) and "available" for the list
            # columns, their sorting and StockStatusFilter
            .with_availability()
        )

    # format_html escapes the arguments and marks the result as safe HTML,
    # so the admin renders <img> instead of showing it as text.
    # Inline styles: the admin doesn't load our styles.css.
    def _cover_img(self, obj, width):
        return format_html(
            '<img src="{}" alt="" style="width: {}px; aspect-ratio: 2 / 3; '
            'object-fit: cover; border-radius: 4px;">',
            obj.cover_url,
            width,
        )

    @admin.display(description=_("cover"))
    def cover_thumbnail(self, obj):
        return self._cover_img(obj, 40)

    @admin.display(description=_("current cover"))
    def cover_preview(self, obj):
        return self._cover_img(obj, 160)

    @admin.display(description=_("categories"))
    def category_list(self, obj):
        return ", ".join(category.name for category in obj.categories.all())

    @admin.display(description=_("stock"), ordering="stock")
    def stock(self, obj):
        return obj.stock

    @admin.display(description=_("available"), boolean=True, ordering="available")
    def is_available(self, obj):
        # A digital format on sale, or paper with copies (with_availability)
        return obj.available


@admin.register(BookFormat)
class BookFormatAdmin(admin.ModelAdmin):
    """One format of a book; the page of a paper book has its copies per warehouse.

    Usually opened from the book page (the link of a format row). The list
    is the quick way to find the formats switched off or priced in a currency.
    """

    list_display = ["__str__", "format_type", "price", "currency", "is_active", "stock"]
    list_filter = ["format_type", "is_active", "currency"]
    # Also for the search-as-you-type of the format in StockAdmin
    search_fields = ["book__title", "book__author__name"]
    autocomplete_fields = ["book"]
    list_select_related = ["book", "currency"]

    def get_queryset(self, request):
        return super().get_queryset(request).with_stock()

    def get_inlines(self, request, obj):
        # Copies only for a saved paper book: a file has no stock
        return [StockInline] if obj is not None and obj.is_paper else []

    @admin.display(description=_("stock"), ordering="stock")
    def stock(self, obj):
        # "—" for a file: it has no copies, 0 would look like "sold out"
        return obj.stock if obj.is_paper else "—"
