from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class WishlistItem(models.Model):
    """A book a user saved with the heart: one row = one book in one user's wishlist.

    Of the book, not of a format: the user likes the book; the format and
    its price are chosen later, on the book page or in the cart.
    Only for logged-in users: a guest has no row to keep it in (the heart
    sends a guest to the login page).
    Deleting the user or the book deletes the row (CASCADE): a wishlist
    is not a record anybody needs to keep, unlike an order.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
        verbose_name=_("user"),
    )
    book = models.ForeignKey(
        "books.Book",
        on_delete=models.CASCADE,
        related_name="wishlist_items",
        verbose_name=_("book"),
    )
    # The order of the wishlist page: the last saved book first
    created_at = models.DateTimeField(_("added"), auto_now_add=True)

    class Meta:
        verbose_name = _("wishlist item")
        verbose_name_plural = _("wishlist items")
        ordering = ["-created_at"]
        constraints = [
            # One book once per user, also for two clicks at the same moment
            # (two tabs): the second insert fails in the database, not only
            # in get_or_create()
            models.UniqueConstraint(fields=["user", "book"], name="wishlist_unique_user_book"),
        ]

    def __str__(self):
        return f"{self.user} ♥ {self.book}"
