"""ViewSets of the catalog: books, their formats, authors, publishers, categories.

A ModelViewSet = 5 actions in one class; the router (api/urls.py) gives
them two URLs:

    GET    /api/books/        list       the list, 20 per page, filters
    POST   /api/books/        create     a new book
    GET    /api/books/<pk>/   retrieve   one book
    PUT    /api/books/<pk>/   update     replace all fields
    PATCH  /api/books/<pk>/   partial_update   only the sent fields
    DELETE /api/books/<pk>/   destroy    204 No Content

Who may do what:
    books       read: everybody; write: the model permissions of the user's
                groups (DjangoModelPermissionsOrAnonReadOnly): add_book for
                POST, change_book for PUT/PATCH, delete_book for DELETE.
                "Editors" add and change, "Managers" also delete.
    formats     the same, with add/change/delete_bookformat (Editors and
                Managers all three); the stock of a paper format only with
                inventory.change_stock (BookFormatSerializer.validate_stock).
                Turned off formats: only for those who may change them.
    authors,    read: everybody; write: IsAdminUser (is_staff) AND the
    publishers, model permission (like the admin): "Managers" may delete a
    categories
                category, a staff member without the permission may not
                (StaffWriteMixin).
"""

import logging

from django.db.models import Count, Prefetch, ProtectedError
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import (
    SAFE_METHODS,
    AllowAny,
    DjangoModelPermissions,
    DjangoModelPermissionsOrAnonReadOnly,
    IsAdminUser,
)

from books.models import Author, Book, BookFormat, Category, Publisher
from currencies.models import BASE_CURRENCY
from currencies.services import available_currencies, current_rates

from ..cache import cache_api_response
from ..docs import (
    author_schema,
    book_schema,
    category_schema,
    format_schema,
    publisher_schema,
)
from ..exceptions import Conflict
from ..filters import BookFilter
from ..serializers.catalog import (
    AuthorSerializer,
    BookFormatSerializer,
    BookSerializer,
    CategorySerializer,
    copy_main_format_to_book,
    PublisherSerializer,
)

logger = logging.getLogger(__name__)  # "api.views.catalog"


class LoggedModelViewSet(viewsets.ModelViewSet):
    """ModelViewSet + a log line for every change + 409 for protected objects.

    The perform_* methods are the hooks of ModelViewSet around save() and
    delete(): the validation and the answer stay DRF's.
    """

    # "Book", "Author", "Category" in the log lines
    log_name = "Object"

    def perform_create(self, serializer):
        instance = serializer.save()
        logger.info(
            "API %s created: id=%s %r by user=%s",
            self.log_name,
            instance.pk,
            str(instance),
            self.request.user.username,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        logger.info(
            "API %s updated: id=%s fields=%s by user=%s",
            self.log_name,
            instance.pk,
            sorted(serializer.validated_data),
            self.request.user.username,
        )

    def perform_destroy(self, instance):
        pk, name = instance.pk, str(instance)
        try:
            instance.delete()
        except ProtectedError:
            # on_delete=PROTECT: an author with books, a category with books,
            # a book in an order. Without this: 500 Internal Server Error
            raise Conflict(self.protected_message)
        logger.info(
            "API %s deleted: id=%s %r by user=%s",
            self.log_name,
            pk,
            name,
            self.request.user.username,
        )


class DisplayCurrencyMixin:
    """?currency=USD: the prices of the answer in this currency (UAH without it).

    Books and formats: "display_price" converted at today's NBU rate, the
    same number the site shows with the currency switcher. The rates are
    read once per request (current_rates(): the cache) and given to the
    serializer and to the SQL of the queryset.
    """

    def display_currency(self):
        """The checked code of ?currency= (UAH without it); 400 for others.

        Only the currencies of the site's switcher: active, with a rate
        today. A client asking for "GBP" gets an error, not prices in UAH
        it would take for pounds.
        """
        if getattr(self, "swagger_fake_view", False):  # building /api/docs/
            return BASE_CURRENCY
        if not hasattr(self, "_display_currency"):
            code = self.request.query_params.get("currency", BASE_CURRENCY).strip().upper()
            offered = [currency.code for currency in available_currencies()]
            if code not in offered:
                raise ValidationError(
                    {
                        "currency": [
                            _("“%(code)s” is not offered. Choose one of: %(offered)s.")
                            % {"code": code, "offered": ", ".join(offered)}
                        ]
                    }
                )
            self._display_currency = code
        return self._display_currency

    def rates(self):
        if not hasattr(self, "_rates"):
            self._rates = current_rates()
        return self._rates

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if getattr(self, "swagger_fake_view", False):  # building /api/docs/: no rates
            return context
        return {**context, "display_currency": self.display_currency(), "rates": self.rates()}


@book_schema
class BookViewSet(DisplayCurrencyMixin, LoggedModelViewSet):
    """Books of the catalog.

    Filters (api.filters.BookFilter): ?category=<slug>, ?author=<id> (both
    may repeat: ?author=1&author=5),
    ?price_min=, ?price_max=, ?stock=in_stock|low|out, ?publisher=<id>,
    ?language=, ?book_type=, ?cover_type= (may repeat), ?year_min=, ?year_max=.
    ?search=kobz  — in the title and the author's name.
    ?ordering=price | -price | title | -created_at | author__name.
    ?currency=USD — display_price in this currency (UAH by default); the
    price filters and the price ordering use display_price too.
    """

    queryset = (
        Book.objects
        # ForeignKey: the author and the publisher in the same SQL query (JOIN)
        .select_related("author", "publisher")
        # ManyToMany: the categories of the whole page in one extra query;
        # the formats on sale with their stock in one more (book.active_formats)
        .prefetch_related(
            "categories",
            Prefetch(
                "formats",
                queryset=BookFormat.objects.filter(is_active=True)
                .select_related("currency")
                .with_stock(),
                to_attr="prefetched_active_formats",
            ),
        )
        # "stock" (of the paper format) and "available" (in_stock) in the
        # same SQL query; also needed by the ?stock= filter
        .with_availability().order_by("title", "pk")
    )
    serializer_class = BookSerializer
    permission_classes = [DjangoModelPermissionsOrAnonReadOnly]
    filterset_class = BookFilter
    search_fields = ["title", "author__name"]
    ordering_fields = ["title", "price", "created_at", "author__name"]
    # ?ordering=price: by the price "from" (api.filters.StableOrderingFilter)
    ordering_aliases = {"price": "display_price"}
    log_name = "Book"
    protected_message = _("The book is in orders and can't be deleted.")

    def get_queryset(self):
        # display_price: the cheapest format on sale, converted by the
        # database, so the filters and the ordering can use it like a column
        queryset = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):  # building /api/docs/
            return queryset
        return queryset.with_display_price(self.display_currency(), rates=self.rates())


@format_schema
class BookFormatViewSet(DisplayCurrencyMixin, LoggedModelViewSet):
    """Formats of the books: paper, e-book, audiobook, each with its own price.

    ?book=<id>            the formats of one book
    ?format_type=paper | ebook | audiobook
    ?is_active=true | false
    ?currency=USD         display_price in this currency

    Read: everybody, the formats on sale; a user who may change formats
    (Editors, Managers) also sees the turned off ones. Write: the model
    permissions of the group (add/change/delete_bookformat). The stock only
    with inventory.change_stock (BookFormatSerializer.validate_stock).
    """

    queryset = BookFormat.objects.select_related("book", "currency").with_stock()
    serializer_class = BookFormatSerializer
    permission_classes = [DjangoModelPermissionsOrAnonReadOnly]
    filterset_fields = ["book", "format_type", "is_active"]
    # Without ?ordering= the order of BookFormat.Meta: by book, paper first
    ordering_fields = ["price"]
    log_name = "BookFormat"
    protected_message = _(
        "The format is in orders and can't be deleted; turn it off instead (is_active: false)."
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.has_perm("books.change_bookformat"):
            return queryset
        return queryset.filter(is_active=True)

    def perform_destroy(self, instance):
        """A book keeps at least one format, like the form of the site (min 1).

        A book without formats has no price at all. To stop selling it,
        the format is turned off (is_active: false), not deleted.
        """
        book = instance.book
        if not book.formats.exclude(pk=instance.pk).exists():
            raise Conflict(
                _(
                    "A book needs at least one format; turn this one off instead "
                    "(is_active: false)."
                )
            )
        super().perform_destroy(instance)
        copy_main_format_to_book(book)


class StaffWriteMixin:
    """Read for everybody; write for staff with the model permission.

    Different permissions for reading and writing: get_permissions() is
    called for every request and returns the list of permission objects
    that must ALL allow it (instead of the fixed permission_classes).

        GET, HEAD, OPTIONS   AllowAny
        POST, PUT, PATCH,    IsAdminUser (request.user.is_staff)
        DELETE               AND DjangoModelPermissions (add_ / change_ /
                             delete_<model> from the user's groups)

    Both, like the Django admin: is_staff opens the door, the group decides
    what may be done ("Managers" delete a category, a staff member without
    a group may not; an editor has add_author but is not staff).
    IsAdminUser alone would let any staff member delete any category.
    """

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdminUser(), DjangoModelPermissions()]


# Whole responses of GET (list and one object) from the cache for
# API_CACHE_TIMEOUT; any change of the catalog drops them (api/signals.py).
# Hits skip the view entirely: no SQL, no throttling counter.
def cache_reads(viewset_class):
    """Class decorator: cache the list and retrieve actions of the ViewSet.

    method_decorator: cache_page is written for functions (request first),
    a ViewSet method gets self first; it adapts one to the other.
    """
    for action in ("list", "retrieve"):
        viewset_class = method_decorator(cache_api_response, name=action)(viewset_class)
    return viewset_class


@author_schema
@cache_reads
class AuthorViewSet(StaffWriteMixin, LoggedModelViewSet):
    """Authors. ?search=<name>, ?ordering=name | -books_count."""

    # Explicit order_by: Meta.ordering is ignored by annotated (GROUP BY) queries
    queryset = Author.objects.annotate(books_count=Count("books")).order_by("name", "pk")
    serializer_class = AuthorSerializer
    search_fields = ["name"]
    ordering_fields = ["name", "books_count"]
    log_name = "Author"
    protected_message = _("The author has books and can't be deleted.")


@publisher_schema
@cache_reads
class PublisherViewSet(StaffWriteMixin, LoggedModelViewSet):
    """Publishers. ?search=<name>, ?ordering=name | -books_count."""

    queryset = Publisher.objects.annotate(books_count=Count("books")).order_by("name", "pk")
    serializer_class = PublisherSerializer
    search_fields = ["name"]
    ordering_fields = ["name", "books_count"]
    log_name = "Publisher"
    protected_message = _("The publisher has books and can't be deleted.")


@category_schema
@cache_reads
class CategoryViewSet(StaffWriteMixin, LoggedModelViewSet):
    """Categories. ?search=<name>, ?ordering=name | -books_count."""

    queryset = Category.objects.annotate(books_count=Count("books")).order_by("name", "pk")
    serializer_class = CategorySerializer
    search_fields = ["name"]
    ordering_fields = ["name", "books_count"]
    log_name = "Category"
    protected_message = _("The category has books and can't be deleted.")
