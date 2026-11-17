from django.contrib import admin

from .models import Rating


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    """The scores of the customers: read, filter by stars, delete (e.g. a wrong one).

    The scores are given by the customers themselves on the book page, so
    the admin does not add or change them.
    """

    list_display = ["book", "user", "score", "updated_at"]
    list_filter = ["score"]
    list_select_related = ["book", "user"]
    search_fields = ["book__title", "user__username", "user__email"]
    date_hierarchy = "updated_at"
    readonly_fields = ["user", "book", "score", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False
