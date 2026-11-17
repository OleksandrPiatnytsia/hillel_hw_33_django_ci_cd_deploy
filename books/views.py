import logging
import math

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.db.models import Case, Count, F, Max, Min, ProtectedError, Q, When
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext
from django.views.decorators.http import require_GET
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from cart.cart import Cart
from ratings.services import rating_context
from currencies.display import display_currency, price_from, request_rates

from .cache import get_cached_book
from .filters import CatalogFilter
from .forms import BookForm, BookFormatFormSet
from .models import Author, Book

logger = logging.getLogger(__name__)  # "books.views"


class ElidedPaginationMixin:
    """Adds page_range ("1 2 … 7 8 9 … 19 20") for templates/includes/pagination.html.

    Templates can't call methods with arguments, so it's computed here.
    """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if context.get("is_paginated"):
            context["page_range"] = context["paginator"].get_elided_page_range(
                context["page_obj"].number, on_each_side=2, on_ends=1
            )
        return context


class BookListView(ElidedPaginationMixin, ListView):
    """Catalog: filters from GET parameters + pagination.

    Template: books/book_list.html (default name: <app>/<model>_list.html)
    """

    model = Book
    context_object_name = "books"
    # Books per page, chosen in the "Per page" dropdown (?per_page=24).
    # Multiples of 2 and 3: the grid has 2 columns (md) and 3 (xl), so every
    # row of the page is full. The first one is the default.
    PER_PAGE_CHOICES = (12, 24, 48)

    def get_paginate_by(self, queryset):
        """?per_page=<n> if n is one of PER_PAGE_CHOICES, else the default.

        Only the listed values: ?per_page=100000 would load the whole catalog
        in one page, and a wrong value (?per_page=abc, an old link) shows the
        default page instead of an error.
        """
        value = self.request.GET.get("per_page", "")
        if value.isdigit() and int(value) in self.PER_PAGE_CHOICES:
            self.per_page = int(value)
        else:
            self.per_page = self.PER_PAGE_CHOICES[0]
        return self.per_page

    def get_queryset(self):
        queryset = (
            super().get_queryset()
            # ForeignKey: author comes in the same SQL query (JOIN)
            .select_related("author")
            # ManyToMany: categories of all books on the page in one extra query
            .prefetch_related("categories")
            # Copies of the paper book in the default warehouse and "can it
            # be bought", in the same SQL query (subqueries): the badge, the
            # "Add to cart" button and "Out of stock last" need them
            .with_availability()
            # The formats on sale of all books on the page in one extra
            # query: the price "from" and the button of the card
            .with_active_formats()
            # The stars of the card and the sort "Best rated" (subqueries)
            .with_rating()
        )

        # A book is sold in formats with own prices in different currencies
        # (paper 650 UAH, e-book 5 USD): "Price from / to" and the sort by
        # price work with the price "from" (the cheapest format on sale) in
        # the currency of the switcher, calculated by the database
        # (Book.objects.with_display_price). The same rounded number the
        # card shows, so "to 14.31 $" includes a book shown as "from 14,31 $".
        self.currency = display_currency(self.request)
        queryset = queryset.with_display_price(
            self.currency.code, rates=request_rates(self.request)
        )

        # The filters (books/filters.py, the same set as the API). Unbound
        # (None) when there are no GET params -> no validation errors.
        self.filterset = CatalogFilter(self.request.GET or None, queryset=queryset)
        # "Price from, $": before the validation, a BoundField copies the
        # label when it is created
        for name in ("price_min", "price_max"):
            field = self.filterset.form.fields[name]
            field.label = f"{field.label}, {self.currency.symbol}"
        # .qs filters with the values that passed the form: one wrong
        # parameter (an old link to a deleted category) shows its error,
        # and the other filters (?q=...) still work, instead of the whole
        # catalog without any filter
        queryset = self.filterset.qs

        # The sort the list is shown with (for the "Sort by" dropdown)
        # Not a filter: read here, an unknown value -> the default
        sort = self.request.GET.get("sort")
        self.sort = sort if sort in dict(CatalogFilter.SORT_CHOICES) else "title"
        # "price" in the URL stays (old links work in any currency), the
        # database sorts by the converted price. nulls_last: a book without
        # a rate (no converted price) goes to the end in both directions.
        ordering = {
            "price": F("display_price").asc(nulls_last=True),
            "-price": F("display_price").desc(nulls_last=True),
        }.get(self.sort, self.sort)
        if self.sort == "-sold":
            # The subquery only for this sort, not on every catalog page;
            # equally popular books (0 sold too) follow by title
            queryset = queryset.with_sold()
            ordering = [F("sold").desc(), "title"]
        elif self.sort == "-rating":
            # The best average first; books without scores at the end; of
            # two equal averages the one with more scores is surer
            ordering = [
                F("rating_avg").desc(nulls_last=True),
                F("rating_count").desc(),
                "title",
            ]
        else:
            ordering = [ordering]
        # "Out of stock last" (the checkbox of the "Sort by" menu, on by
        # default, ?out_last=0 turns it off): the books that can't be bought
        # go after all the others, the chosen sort works inside both groups.
        # "available" comes from with_availability() above, in the same
        # query: a sold out paper book with an e-book on sale is not last.
        self.out_last = self.request.GET.get("out_last") != "0"
        if self.out_last:
            ordering.insert(0, Case(When(available=False, then=1), default=0))
        # Always with "pk" as a tie-breaker, the default sort (Book.Meta.ordering
        # = title) too: books with an equal title or price keep a stable order,
        # so the same book doesn't jump between pages
        return queryset.order_by(*ordering, "pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filterset.form
        # The active filters above the list ("x" removes one) and "Clear all"
        context["filter_chips"] = self.filterset.chips(self.currency.symbol)
        context["filter_reset_url"] = self.filterset.reset_url()
        # For the "Per page" dropdown and the hidden field of the filter form
        context["per_page"] = self.per_page
        context["per_page_choices"] = self.PER_PAGE_CHOICES
        # "Sort by" dropdown next to "Per page": every choice is a link,
        # the current one is marked; the button shows its label
        context["sort_choices"] = CatalogFilter.SORT_CHOICES
        context["sort"] = self.sort
        context["sort_label"] = dict(CatalogFilter.SORT_CHOICES)[self.sort]
        context["out_last"] = self.out_last
        # Timeout of the {% cache %} fragments of the book cards
        context["cache_timeout"] = settings.BOOK_CACHE_TIMEOUT
        context["price_range"] = self.price_range()
        context["year_range"] = self.year_range()
        return context

    def year_range(self):
        """The oldest and the newest edition of the catalog: the hints of the year block.

        Of the whole catalog, like the price slider. None when no book has a
        year: then the block is not shown (unless a year is in the URL).
        """
        years = Book.objects.aggregate(low=Min("publication_year"), high=Max("publication_year"))
        if years["low"] is None:
            return None
        return {"min": years["low"], "max": years["high"]}

    def price_range(self):
        """The ends of the price slider: the cheapest and the dearest price "from".

        Of the whole catalog in the currency of the switcher, not of the
        filtered list: then the slider keeps its scale while the user moves
        it. Whole numbers outward (12.40 .. 1510.99 -> 12 .. 1511), so the
        ends include every book. One SQL query (MIN and MAX of the same CASE
        as the filter). None when there is nothing to slide: no books, or
        all of them at one price.
        """
        books = Book.objects.with_display_price(
            self.currency.code, rates=request_rates(self.request)
        )
        bounds = books.aggregate(low=Min("display_price"), high=Max("display_price"))
        if bounds["low"] is None:
            return None
        low, high = math.floor(bounds["low"]), math.ceil(bounds["high"])
        return {"min": low, "max": high} if low < high else None


class BookDetailView(DetailView):
    """Single book. Template: books/book_detail.html

    The book (with author and categories) comes from the cache
    (books.cache.get_cached_book): a cache hit needs no query for it.
    Only the stock is read every time: one small query when the template
    asks for book.stock (it is never cached, orders change it); the paper
    format of the tiles gets the same number, no second query.
    """

    model = Book
    context_object_name = "book"

    def get_object(self, queryset=None):
        try:
            return get_cached_book(self.kwargs["pk"])
        except Book.DoesNotExist:
            # The same 404 page as DetailView's own get_object()
            raise Http404 from None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cache_timeout"] = settings.BOOK_CACHE_TIMEOUT
        book = self.object
        # The stock of the paper book is the stock of its paper format:
        # read once (book.stock), given to the format of the tile
        if book.paper_format is not None:
            book.paper_format.stock = book.stock
        # "In your cart: Paper — 2" under the button. Templates can't call
        # a method with an argument (cart.lines_of(book)), so it's done here.
        context["in_cart"] = Cart(self.request).lines_of(book)
        context.update(rating_context(self.request.user, book))
        return context


# PermissionRequiredMixin goes FIRST (left of CreateView / UpdateView /
# DeleteView): its dispatch() must run before the view's own dispatch().
# What it does when has_perm() is False:
#   - anonymous user -> redirect to LOGIN_URL with ?next=<this page>
#   - logged-in user without the permission -> 403 (templates/403.html)
# So a separate LoginRequiredMixin is not needed here.


class BookFormatsMixin:
    """The book form + the rows of its formats (BookFormatFormSet) on one page.

    Both are checked before anything is saved: a valid book with a wrong
    format (an e-book with a cover) shows the page again with the error,
    and nothing is written. Then the book and its formats are saved in one
    transaction.
    """

    def get_formats(self):
        if not hasattr(self, "formats"):
            self.formats = BookFormatFormSet(
                data=self.request.POST if self.request.method == "POST" else None,
                # A new book: an empty Book, the rows have nothing to load
                instance=self.object or Book(),
                prefix="formats",
            )
        return self.formats

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["formats"] = self.get_formats()
        return context

    def post(self, request, *args, **kwargs):
        # CreateView: no object yet; UpdateView: the edited book
        self.object = self.get_object() if "pk" in self.kwargs else None
        form = self.get_form()
        # Both validated, so the page shows the errors of both at once
        form_ok, formats_ok = form.is_valid(), self.get_formats().is_valid()
        if form_ok and formats_ok:
            return self.form_valid(form)
        return self.form_invalid(form)

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)  # saves the book -> self.object
            self.formats.instance = self.object
            self.formats.save()
        return response


class BookCreateView(PermissionRequiredMixin, SuccessMessageMixin, BookFormatsMixin, CreateView):
    """New book. Template: books/book_form.html (shared with update).

    No success_url: after saving, Django redirects to book.get_absolute_url().
    """

    permission_required = "books.add_book"
    model = Book
    form_class = BookForm
    success_message = _("Book “%(title)s” was created.")

    def form_valid(self, form):
        response = super().form_valid(form)  # saves -> self.object has a pk
        logger.info(
            "Book created: id=%s title=%r stock=%s by user=%s",
            self.object.pk,
            self.object.title,
            self.object.stock,
            self.request.user.username,
        )
        return response


class BookUpdateView(PermissionRequiredMixin, SuccessMessageMixin, BookFormatsMixin, UpdateView):
    """Edit a book. Template: books/book_form.html (shared with create)."""

    permission_required = "books.change_book"
    model = Book
    form_class = BookForm
    success_message = _("Book “%(title)s” was updated.")

    def form_valid(self, form):
        response = super().form_valid(form)
        # changed_data: names of fields whose value differs from the initial
        # one — shows WHAT was edited, not just "something changed"
        logger.info(
            "Book updated: id=%s title=%r changed=%s by user=%s",
            self.object.pk,
            self.object.title,
            form.changed_data or "nothing",
            self.request.user.username,
        )
        return response


class BookDeleteView(PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    """GET -> confirmation page, POST -> delete.

    Template: books/book_confirm_delete.html

    A book that is in orders can't be deleted: OrderItem.book has
    on_delete=PROTECT, the order history must stay complete. Then:
    - GET: the page says so at once (orders_count) and has no delete button,
      only "Edit in admin" (stock = 0 stops the sales);
    - POST anyway (an old open tab, or the book was ordered after the page
      was opened): delete() raises ProtectedError -> an error message and
      back to the book, instead of 500.
    """

    permission_required = "books.delete_book"
    model = Book
    context_object_name = "book"
    success_url = reverse_lazy("books:list")
    # the confirmation page shows the author's name
    queryset = Book.objects.select_related("author")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Lines of orders with this book = orders: one line per book in an
        # order (unique constraint of OrderItem)
        context["orders_count"] = self.object.order_items.count()
        return context

    def form_valid(self, form):
        # Remember pk BEFORE deleting: after delete() Django sets it to None
        book_id = self.object.pk
        try:
            response = super().form_valid(form)
        except ProtectedError:
            # Raised while Django collects the related rows, before any
            # DELETE: nothing is deleted. SuccessMessageMixin adds its
            # message after super().form_valid(), so no "was deleted" either.
            logger.warning(
                "Book not deleted, it is in orders: id=%s title=%r by user=%s",
                book_id,
                self.object.title,
                self.request.user.username,
            )
            messages.error(
                self.request,
                gettext(
                    "“%(title)s” is in orders and can't be deleted. "
                    "Set its stock to 0 to stop selling it."
                )
                % {"title": self.object.title},
            )
            return redirect(self.object)
        logger.info(
            "Book deleted: id=%s title=%r by user=%s",
            book_id,
            self.object.title,
            self.request.user.username,
        )
        return response

    def get_success_message(self, cleaned_data):
        # Delete form has no fields, so take the title from the deleted object
        return gettext("Book “%(title)s” was deleted.") % {"title": self.object.title}


# ---------------------------------------------------------------------------
# Authors: read-only pages. Adding / editing authors is done in the admin.
# ---------------------------------------------------------------------------


class AuthorListView(ElidedPaginationMixin, ListView):
    """All authors with the number of their books. Template: books/author_list.html"""

    model = Author
    context_object_name = "authors"
    paginate_by = 20

    def get_queryset(self):
        # Explicit order_by: Meta.ordering is ignored for annotated (GROUP BY) queries
        return Author.objects.annotate(books_count=Count("books")).order_by("name")


class AuthorDetailView(DetailView):
    """Author + their books. Template: books/author_detail.html"""

    model = Author
    context_object_name = "author"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Reverse side of ForeignKey: related_name="books" -> author.books
        context["books"] = (
            self.object.books.prefetch_related("categories").with_stock().with_active_formats()
        )
        return context


# ---------------------------------------------------------------------------
# Search suggestions for the navbar (async)
# ---------------------------------------------------------------------------

SEARCH_MIN_LENGTH = 2  # fewer letters match half the catalog
SEARCH_LIMIT = 8  # suggestions in the dropdown


@require_GET
async def book_search(request):
    """GET /search/?q=kob -> JSON: up to 8 books whose title or author matches.

    Used by the search field in the navbar (static/js/book_search.js) while
    the user types; Enter still opens the full catalog search (?q=...).

    Async view, async ORM: `async for` over the queryset sends the query
    without blocking the event loop (the same Q filter as BookListView).
    """
    query = request.GET.get("q", "").strip()
    if len(query) < SEARCH_MIN_LENGTH:
        return JsonResponse({"results": []})

    books = (
        Book.objects.select_related("author")  # author.name in the same query
        # "Can it be bought" in the same query: book.available without it
        # would be a sync query inside an async view (SynchronousOnlyOperation)
        .with_availability()
        # The formats for the price "from": prefetch_related works with
        # `async for` too (one more query, not one per book)
        .with_active_formats()
        .filter(Q(title__icontains=query) | Q(author__name__icontains=query))
        .order_by("title", "pk")[:SEARCH_LIMIT]
    )
    books = [book async for book in books]
    # The prices in the currency of the switcher: display_currency() reads
    # the session and the cached rates, which are sync code, so it runs in
    # a thread (sync_to_async), like the ORM would without `async for`
    prices = await sync_to_async(lambda: [_price_text(request, book) for book in books])()
    results = [
        {
            "title": book.title,
            "author": book.author.name,
            "url": book.get_absolute_url(),
            # "250,00 ₴" / "$5.50": the language and the currency of the request
            "price": price,
            # A sold out paper book with an e-book on sale: still true
            "in_stock": book.available,
        }
        for book, price in zip(books, prices)
    ]
    return JsonResponse({"results": results})


def _price_text(request, book):
    """ "250,00 ₴", "from 199,00 ₴" (several formats) or "" (nothing on sale)."""
    price = price_from(request, book)
    if price is None:
        return ""
    if len(book.active_formats) > 1:
        return gettext("from %(price)s") % {"price": price}
    return str(price)
