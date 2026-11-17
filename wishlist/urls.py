from django.urls import path

from . import views

# Namespace: "wishlist:detail", "wishlist:add", "wishlist:remove"
app_name = "wishlist"

urlpatterns = [
    path("", views.WishlistView.as_view(), name="detail"),
    # Two URLs instead of one "toggle": the heart says what it wants. With
    # a toggle, a page left open in another tab would undo the change of
    # this one; "add" twice or "remove" twice changes nothing
    path("add/<int:book_id>/", views.wishlist_add, name="add"),
    path("remove/<int:book_id>/", views.wishlist_remove, name="remove"),
]
