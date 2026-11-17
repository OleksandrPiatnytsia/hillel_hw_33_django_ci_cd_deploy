"""The wishlist: the hearts (add / remove) and the page of the saved books.

The heart is a POST form (it changes data: a GET link could be triggered by
another site or by a browser that prefetches links). Two ways it is sent:
- static/js/wishlist.js sends it with fetch() and asks for JSON
  (Accept: application/json): the heart changes in place, no reload;
- without JavaScript the browser sends it as usual: a message and a
  redirect back to the page ("next").
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from books.models import Book
from books.views import ElidedPaginationMixin

from .models import WishlistItem


def _wants_json(request):
    return "application/json" in request.headers.get("Accept", "")


def _next_url(request):
    """The page to go back to: the "next" form field if it is of this site, or the wishlist.

    The check refuses addresses of other sites (open redirect).
    """
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse("wishlist:detail")


def _answer(request, book, saved, message):
    """The answer of add / remove: JSON for the script, else a message and a redirect.

    JSON: the new state of the heart and the URL its form must send next
    time (add <-> remove).
    """
    if _wants_json(request):
        action = "wishlist:remove" if saved else "wishlist:add"
        return JsonResponse(
            {
                "saved": saved,
                "url": reverse(action, args=[book.pk]),
                "message": message,
            }
        )
    messages.success(request, message)
    return redirect(_next_url(request))


def _login_first(request):
    """A guest (or a session that has expired): the wishlist needs an account.

    The heart of a guest is a link to the login page, so this is only a
    form sent after the session ended. JSON: 401 + where to log in, the
    script opens it; else the login page, back to the page after it.
    """
    # /accounts/login/?next=<the page of the heart>
    login = redirect_to_login(_next_url(request))
    if _wants_json(request):
        return JsonResponse({"login_url": login.url}, status=401)
    return login


@require_POST
def wishlist_add(request, book_id):
    """POST /wishlist/add/<book_id>/ -> the book is in the wishlist (again: no change)."""
    if not request.user.is_authenticated:
        return _login_first(request)
    book = get_object_or_404(Book, pk=book_id)
    # get_or_create: a second click (two tabs) is not an error
    WishlistItem.objects.get_or_create(user=request.user, book=book)
    return _answer(
        request, book, True, _("“%(title)s” is in your wishlist.") % {"title": book.title}
    )


@require_POST
def wishlist_remove(request, book_id):
    """POST /wishlist/remove/<book_id>/ -> the book is not in the wishlist (no change if not)."""
    if not request.user.is_authenticated:
        return _login_first(request)
    book = get_object_or_404(Book, pk=book_id)
    WishlistItem.objects.filter(user=request.user, book=book).delete()
    return _answer(
        request,
        book,
        False,
        _("“%(title)s” is removed from your wishlist.") % {"title": book.title},
    )


class WishlistView(LoginRequiredMixin, ElidedPaginationMixin, ListView):
    """/wishlist/: the books the user saved, the last saved first, as catalog cards.

    LoginRequiredMixin: a guest goes to the login page and comes back here.
    The same data as the catalog cards need (books/includes/book_card.html):
    the price "from", the stock badge and the "Add to cart" button.
    """

    template_name = "wishlist/wishlist.html"
    context_object_name = "books"
    paginate_by = 24

    def get_queryset(self):
        return (
            Book.objects.filter(wishlist_items__user=self.request.user)
            # The same join as the filter above (one row of the user per
            # book): the date the book was saved
            .order_by("-wishlist_items__created_at", "title")
            .select_related("author")
            .prefetch_related("categories")
            .with_availability()
            .with_active_formats()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The cached fragment of the card (book_card), as in the catalog
        context["cache_timeout"] = settings.BOOK_CACHE_TIMEOUT
        return context
