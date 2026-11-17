from django.contrib import admin

from .models import WishlistItem


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    """Read the wishlists: which books are saved most, by whom.

    Rows are made by the users themselves (the heart), so the admin only
    shows and deletes them.
    """

    list_display = ["book", "user", "created_at"]
    list_select_related = ["book", "user"]
    search_fields = ["book__title", "user__username", "user__email"]
    date_hierarchy = "created_at"
    readonly_fields = ["user", "book", "created_at"]

    def has_add_permission(self, request):
        return False
