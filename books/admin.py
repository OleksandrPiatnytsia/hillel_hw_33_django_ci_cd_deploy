from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from inventory.models import Stock

from .models import Author, Book, BookCategory, BookQuerySet, Category

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
    """Copies of the book per warehouse, on the Book page.

    Editable only with inventory.change_stock (group "Managers"): Django
    shows the rows read-only for users with only view_stock (Editors).
    """

    model = Stock
    extra = 0
    fields = ["warehouse", "quantity"]
    verbose_name = _("stock")
    verbose_name_plural = _("stock")

    def has_add_permission(self, request, obj=None):
        # A new book (obj is None): no rows here. Its row in the default
        # warehouse is made by inventory.signals right after the book is
        # saved; a row from this form for the same warehouse would then
        # break the unique (book, warehouse) constraint.
        if obj is None:
            return False
        return super().has_add_permission(request, obj)


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


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = [
        "cover_thumbnail",
        "title",
        "author",
        "price",
        "stock",
        "is_available",
        "category_list",
        "created_at",
    ]
    list_display_links = ["title"]
    # No "stock" here: it is a value of inventory.Stock, not a column of
    # the book; quantities are edited in the Stock list or on the book page
    list_editable = ["price"]
    list_filter = [StockStatusFilter, "categories", "created_at"]
    search_fields = ["title", "author__name", "description", "categories__name"]
    date_hierarchy = "created_at"
    # Search-as-you-type instead of a <select> with every author
    # (needs search_fields in AuthorAdmin)
    autocomplete_fields = ["author"]
    readonly_fields = ["cover_preview", "created_at", "updated_at"]
    inlines = [StockInline, BookCategoryInline]
    fieldsets = [
        (None, {"fields": ["title", "author", "description"]}),
        (_("Cover"), {"fields": ["cover_preview", "cover"]}),
        (_("Sales"), {"fields": ["price"]}),
        (
            _("Timestamps"),
            {"fields": ["created_at", "updated_at"], "classes": ["collapse"]},
        ),
    ]

    def get_queryset(self, request):
        # Author via JOIN, categories in one extra query — not a query per row
        return (
            super()
            .get_queryset(request)
            .select_related("author")
            .prefetch_related("categories")
            # "stock" for the list column, its sorting and StockStatusFilter
            .with_stock()
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

    @admin.display(description=_("available"), boolean=True, ordering="stock")
    def is_available(self, obj):
        return obj.stock > 0
