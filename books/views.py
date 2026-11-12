import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, ProtectedError, Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.formats import number_format
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

from .cache import get_cached_book
from .forms import BookFilterForm, BookForm
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
            super()
            .get_queryset()
            # ForeignKey: author comes in the same SQL query (JOIN)
            .select_related("author")
            # ManyToMany: categories of all books on the page in one extra query
            .prefetch_related("categories")
            # Copies in the default warehouse, in the same SQL query
            # (a subquery): the badge and the "Add to cart" button need it
            .with_stock()
        )

        # Unbound form (None) when there are no GET params -> no validation errors
        self.filter_form = BookFilterForm(self.request.GET or None)
        # After is_valid() cleaned_data holds only the fields that passed:
        # one wrong parameter (an old link to a deleted category) shows its
        # error, and the other filters (?q=...) still work, instead of the
        # whole catalog without any filter
        self.filter_form.is_valid()
        data = getattr(self.filter_form, "cleaned_data", {})  # unbound: none

        if data.get("q"):
            queryset = queryset.filter(
                Q(title__icontains=data["q"]) | Q(author__name__icontains=data["q"])
            )
        if data.get("category"):
            queryset = queryset.filter(categories=data["category"])
        if data.get("author"):
            queryset = queryset.filter(author=data["author"])
        queryset = queryset.by_stock_status(data.get("stock"))
        if data.get("price_min") is not None:
            queryset = queryset.filter(price__gte=data["price_min"])
        if data.get("price_max") is not None:
            queryset = queryset.filter(price__lte=data["price_max"])
        # Always with "pk" as a tie-breaker, the default sort (Book.Meta.ordering
        # = title) too: books with an equal title or price keep a stable order,
        # so the same book doesn't jump between pages
        return queryset.order_by(data.get("sort") or "title", "pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        # For the "Per page" dropdown and the hidden field of the filter form
        context["per_page"] = self.per_page
        context["per_page_choices"] = self.PER_PAGE_CHOICES
        # Timeout of the {% cache %} fragments of the book cards
        context["cache_timeout"] = settings.BOOK_CACHE_TIMEOUT
        return context


class BookDetailView(DetailView):
    """Single book. Template: books/book_detail.html

    The book (with author and categories) comes from the cache
    (books.cache.get_cached_book): a cache hit needs no query for it.
    Only the stock is read every time: one small query when the template
    asks for book.stock (it is never cached, orders change it).
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
        # "In your cart: 2" under the button. Templates can't call a method
        # with an argument (cart.quantity_of(book)), so it's computed here.
        context["in_cart"] = Cart(self.request).quantity_of(self.object)
        return context


class BookFormUserMixin:
    """Passes the current user to BookForm (it decides whether "stock" is editable)."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


# PermissionRequiredMixin goes FIRST (left of CreateView / UpdateView /
# DeleteView): its dispatch() must run before the view's own dispatch().
# What it does when has_perm() is False:
#   - anonymous user -> redirect to LOGIN_URL with ?next=<this page>
#   - logged-in user without the permission -> 403 (templates/403.html)
# So a separate LoginRequiredMixin is not needed here.


class BookCreateView(
    PermissionRequiredMixin, BookFormUserMixin, SuccessMessageMixin, CreateView
):
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


class BookUpdateView(
    PermissionRequiredMixin, BookFormUserMixin, SuccessMessageMixin, UpdateView
):
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
      only "Edit" (stock = 0 stops the sales);
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
        context["books"] = self.object.books.prefetch_related("categories").with_stock()
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
        # The stock in the same query: book.stock without it would be a
        # sync query inside an async view (SynchronousOnlyOperation)
        .with_stock()
        .filter(Q(title__icontains=query) | Q(author__name__icontains=query))
        .order_by("title", "pk")[:SEARCH_LIMIT]
    )
    results = [
        {
            "title": book.title,
            "author": book.author.name,
            "url": book.get_absolute_url(),
            # "250,00" / "250.00": in the language of the request
            "price": number_format(book.price, 2),
            "in_stock": book.stock > 0,
        }
        async for book in books
    ]
    return JsonResponse({"results": results})
