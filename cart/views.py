from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from books.models import Book, BookFormat

from .cart import Cart
from .forms import CartAddForm, CartFormatForm


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


def _formats():
    # The book for the messages, the stock for Cart.add()
    return BookFormat.objects.select_related("book").with_stock()


def _label(book_format):
    """ "Кобзар (Паперова)": the title of the book with its format, for the messages."""
    return f"{book_format.book.title} ({book_format.get_format_type_display()})"


def _report(request, book_format, quantity):
    """The message after a change of the quantity: added, cut to the stock, or refused."""
    title = _label(book_format)
    if quantity == 0:
        if not book_format.is_active:
            messages.error(request, _("“%(title)s” is not on sale.") % {"title": title})
        else:
            messages.error(request, _("“%(title)s” is out of stock.") % {"title": title})
    elif book_format.is_paper and quantity == book_format.stock:
        # Either exactly the stock was asked for, or more and Cart.add() cut it
        messages.warning(
            request,
            _("“%(title)s”: %(quantity)s in the cart, that's all we have in stock.")
            % {"title": title, "quantity": quantity},
        )
    else:
        messages.success(
            request,
            _("“%(title)s”: %(quantity)s in the cart.") % {"title": title, "quantity": quantity},
        )


def cart_detail(request):
    """Cart page. "cart" in the template comes from the context processor."""
    return render(request, "cart/cart_detail.html")


# require_POST: changes only by POST (a form with a CSRF token). A GET link
# could be triggered by another site or a prefetching browser.
# GET -> 405 Method Not Allowed.
@require_POST
def cart_add(request, book_id):
    """Add copies of a format of the book (override=False) or set the quantity (override=True).

    The format comes in the form field "format" (the tiles of the book
    page, a hidden field of the card); it must be a format of THIS book,
    otherwise 404. Without it: the main format of the book (Book.main_format).
    """
    book = get_object_or_404(Book.objects.with_active_formats(), pk=book_id)
    form = CartAddForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Quantity must be a whole number, 1 or more."))
        return _redirect_back(request)

    format_id = form.cleaned_data["format"]
    if format_id is None:
        main_format = book.main_format
        if main_format is None:
            messages.error(request, _("“%(title)s” is not on sale.") % {"title": book.title})
            return _redirect_back(request)
        format_id = main_format.pk
    book_format = get_object_or_404(_formats(), pk=format_id, book=book)

    quantity = Cart(request).add(
        book_format,
        quantity=form.cleaned_data["quantity"],
        override=form.cleaned_data["override"],
    )
    _report(request, book_format, quantity)
    return _redirect_back(request)


@require_POST
def cart_change_format(request, format_id):
    """POST /cart/format/<format_id>/ format=<id> -> the line gets another format of the book.

    The "Format" select of a cart line (sent by static/js/auto_submit.js
    when it changes, or by its button without JavaScript). The new format
    must be of the same book, otherwise 404. Not on sale or out of stock:
    the line stays as it was, with a message.

    No "added to the cart" message: nothing was added, the user sees the
    new format in the line. A message only when something went not as
    asked: refused (the line stays) or cut to the stock of the paper book.
    """
    book_format = get_object_or_404(_formats(), pk=format_id)
    form = CartFormatForm(request.POST)
    if not form.is_valid():
        return _redirect_back(request)
    new_format = get_object_or_404(
        _formats(), pk=form.cleaned_data["format"], book=book_format.book
    )

    cart = Cart(request)
    if not cart.quantity_of(book_format) or new_format.pk == book_format.pk:
        return _redirect_back(request)
    # The quantity the line should get: its own + the copies of new_format
    # already in the cart (the two lines become one)
    wanted = cart.quantity_of(book_format) + cart.quantity_of(new_format)
    quantity = cart.change_format(book_format, new_format)
    if quantity < wanted:
        _report(request, new_format, quantity)
    return _redirect_back(request)


@require_POST
def cart_remove(request, format_id):
    """POST /cart/remove/<format_id>/ -> remove all copies of the format from the cart.

    The "×" button on the cart page. POST only: a GET link could be opened
    by a browser prefetch or a crawler and empty the cart by itself.
    A missing format -> 404. Afterwards back to the page the user came from
    (_redirect_back: only to this site), with a message.
    """
    book_format = get_object_or_404(_formats(), pk=format_id)
    Cart(request).remove(book_format)
    messages.success(
        request, _("“%(title)s” removed from the cart.") % {"title": _label(book_format)}
    )
    return _redirect_back(request)


@require_POST
def cart_clear(request):
    """POST /cart/clear/ -> empty the whole cart, then the (empty) cart page.

    The "Clear cart" button. Only the session key of the cart is removed;
    the rest of the session (login, language) stays.
    """
    Cart(request).clear()
    messages.success(request, _("The cart is empty now."))
    return redirect("cart:detail")
