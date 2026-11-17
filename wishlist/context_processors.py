from django.utils.functional import SimpleLazyObject

from .wishlist import Wishlist


def wishlist(request):
    """Adds "wishlist" to the context of every template rendered with a request.

    The hearts ({% if book.pk in wishlist %}) and the count in the profile.
    SimpleLazyObject + Wishlist.book_ids: a page without a heart or for a
    guest makes no query; a page with many hearts makes one.
    """
    return {"wishlist": SimpleLazyObject(lambda: Wishlist(request.user))}
