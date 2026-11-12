"""ViewSets of the catalog: books, authors, categories.

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
                "Editors" add and change, "Managers" also delete. The stock
                only with inventory.change_stock (BookSerializer.validate_stock).
    authors,    read: everybody; write: IsAdminUser (is_staff) AND the
    categories  model permission (like the admin): "Managers" may delete a
                category, a staff member without the permission may not
                (StaffWriteMixin).
"""

import logging

from django.db.models import Count, ProtectedError
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets
from rest_framework.permissions import (
    SAFE_METHODS,
    AllowAny,
    DjangoModelPermissions,
    DjangoModelPermissionsOrAnonReadOnly,
    IsAdminUser,
)

from books.models import Author, Book, Category

from ..cache import cache_api_response
from ..docs import author_schema, book_schema, category_schema
from ..exceptions import Conflict
from ..filters import BookFilter
from ..serializers.catalog import AuthorSerializer, BookSerializer, CategorySerializer

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


@book_schema
class BookViewSet(LoggedModelViewSet):
    """Books of the catalog.

    Filters (api.filters.BookFilter): ?category=<slug>, ?author=<id>,
    ?price_min=, ?price_max=, ?stock=in_stock|low|out.
    ?search=kobz  — in the title and the author's name.
    ?ordering=price | -price | title | -created_at | author__name.
    """

    queryset = (
        Book.objects
        # ForeignKey: the author in the same SQL query (JOIN)
        .select_related("author")
        # ManyToMany: the categories of the whole page in one extra query
        .prefetch_related("categories")
        # "stock" of the default warehouse in the same SQL query; also
        # needed by the ?stock= filter
        .with_stock().order_by("title", "pk")
    )
    serializer_class = BookSerializer
    permission_classes = [DjangoModelPermissionsOrAnonReadOnly]
    filterset_class = BookFilter
    search_fields = ["title", "author__name"]
    ordering_fields = ["title", "price", "created_at", "author__name"]
    log_name = "Book"
    protected_message = _("The book is in orders and can't be deleted.")


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
