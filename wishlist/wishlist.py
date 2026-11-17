"""The wishlist of the current visitor, for the templates and the views."""

from functools import cached_property

from .models import WishlistItem


class Wishlist:
    """The ids of the books the current user saved.

    One SQL query per request, and only when a template asks (a heart or
    the count of the profile): cached_property. A guest has an empty
    wishlist without any query.

        {% if book.pk in wishlist %}   -> __contains__
        {{ wishlist|length }}          -> __len__
    """

    def __init__(self, user):
        self.user = user

    @cached_property
    def book_ids(self):
        if not self.user.is_authenticated:
            return frozenset()
        return frozenset(
            WishlistItem.objects.filter(user=self.user).values_list("book_id", flat=True)
        )

    def __contains__(self, book):
        # A Book or its pk: {% if book in wishlist %} works too
        return getattr(book, "pk", book) in self.book_ids

    def __len__(self):
        return len(self.book_ids)

    def __bool__(self):
        return bool(self.book_ids)
