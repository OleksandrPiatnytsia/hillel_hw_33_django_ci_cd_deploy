from django.contrib import admin

from .models import Stock, Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_default"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    """All stock rows (paper books only): the quick way to change many quantities at once.

    list_editable here instead of the old "stock" column of the book list:
    the quantity is a field of Stock now, not of Book.
    """

    list_display = ["format", "warehouse", "quantity"]
    list_editable = ["quantity"]
    list_filter = ["warehouse"]
    search_fields = ["format__book__title", "format__book__author__name"]
    # Search-as-you-type for the format (BookFormatAdmin has search_fields);
    # Stock.clean() refuses an e-book or an audiobook
    autocomplete_fields = ["format"]
    # format + its book for str(format), warehouse: JOINs instead of queries per row
    list_select_related = ["format__book", "warehouse"]
