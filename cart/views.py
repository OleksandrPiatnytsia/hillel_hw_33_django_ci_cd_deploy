from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from books.models import Book

from .cart import Cart
from .forms import CartAddForm


def _redirect_back(request):
    """Redirect to ?next= / the "next" form field, or to the cart page.

    The catalog sends next=<current page with filters>, so after "Add to cart"
    the user stays on the same page. The check refuses addresses of other
    sites (open redirect: next=https://evil.example/ would send the user away).
    """
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("cart:detail")


def cart_detail(request):
    """Cart page. "cart" in the template comes from the context processor."""
    return render(request, "cart/cart_detail.html")


# require_POST: changes only by POST (a form with a CSRF token). A GET link
# could be triggered by another site or a prefetching browser.
# GET -> 405 Method Not Allowed.
@require_POST
def cart_add(request, book_id):
    """Add copies of a book (override=False) or set the quantity (override=True)."""
    # with_stock(): Cart.add() and the messages below read book.stock
    book = get_object_or_404(Book.objects.with_stock(), pk=book_id)
    form = CartAddForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Quantity must be a whole number, 1 or more."))
        return _redirect_back(request)

    quantity = Cart(request).add(
        book,
        quantity=form.cleaned_data["quantity"],
        override=form.cleaned_data["override"],
    )

    if quantity == 0:
        messages.error(request, _("“%(title)s” is out of stock.") % {"title": book.title})
    elif quantity == book.stock:
        # Either exactly the stock was asked for, or more and Cart.add() cut it
        messages.warning(
            request,
            _("“%(title)s”: %(quantity)s in the cart, that's all we have in stock.")
            % {"title": book.title, "quantity": quantity},
        )
    else:
        messages.success(
            request,
            _("“%(title)s”: %(quantity)s in the cart.")
            % {"title": book.title, "quantity": quantity},
        )
    return _redirect_back(request)


@require_POST
def cart_remove(request, book_id):
    """POST /cart/remove/<book_id>/ -> remove all copies of the book from the cart.

    The "×" button on the cart page. POST only: a GET link could be opened
    by a browser prefetch or a crawler and empty the cart by itself.
    A missing book -> 404. Afterwards back to the page the user came from
    (_redirect_back: only to this site), with a message.
    """
    book = get_object_or_404(Book, pk=book_id)
    Cart(request).remove(book)
    messages.success(request, _("“%(title)s” removed from the cart.") % {"title": book.title})
    return _redirect_back(request)


@require_POST
def cart_clear(request):
    """POST /cart/clear/ -> empty the whole cart, then the (empty) cart page.

    The "Clear cart" button. Only the session key "cart" is removed; the
    rest of the session (login, language) stays.
    """
    Cart(request).clear()
    messages.success(request, _("The cart is empty now."))
    return redirect("cart:detail")
