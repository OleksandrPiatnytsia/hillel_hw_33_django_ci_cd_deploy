from django.urls import path

from . import views

# Namespace: "cart:detail", "cart:add", ...
app_name = "cart"

urlpatterns = [
    path("", views.cart_detail, name="detail"),
    # By book: the format comes in the form ("format"), the book page and
    # the catalog card post here
    path("add/<int:book_id>/", views.cart_add, name="add"),
    # By format: a line of the cart
    path("remove/<int:format_id>/", views.cart_remove, name="remove"),
    path("format/<int:format_id>/", views.cart_change_format, name="change_format"),
    path("clear/", views.cart_clear, name="clear"),
]
