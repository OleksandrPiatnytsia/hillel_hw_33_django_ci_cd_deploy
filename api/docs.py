"""Texts of the API documentation (/api/docs/, /api/redoc/) for the clients.

drf-spectacular builds the documentation from the code: the URLs, the
serializers (fields and types), the filters. The descriptions it takes
from the docstrings; ours are written for the developers of this project
("get_queryset() ... IsOwnerOrReadOnly"). extend_schema(summary=...,
description=...) puts a text for the user of the API in their place.

The texts are in English, like the rest of the API (field names, codes).
"""

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)

from .serializers.catalog import AuthorSerializer, BookSerializer, CategorySerializer
from .serializers.orders import OrderSerializer

# Common answers, reused by several endpoints
UNAUTHORIZED = OpenApiResponse(description="No valid token or session (401).")
FORBIDDEN = OpenApiResponse(description="Logged in, but not allowed (403).")
NOT_FOUND = OpenApiResponse(description="No such object (404).")


def catalog_schema(serializer, singular, plural, who_writes, *, protected):
    """extend_schema_view for a catalog ViewSet: the 6 actions of a ModelViewSet.

    serializer: the answer of the actions (responses= replaces the default
    one, so it is given again; None there would mean "no body");
    singular / plural: "book" / "books"; who_writes: one sentence on the
    permissions; protected: when DELETE answers 409.
    """
    write_errors = {401: UNAUTHORIZED, 403: FORBIDDEN}
    # "a book", "an author"
    a = "an" if singular[0] in "aeiou" else "a"
    return extend_schema_view(
        list=extend_schema(
            summary=f"List {plural}",
            description=f"Open to everybody. 20 {plural} per page: ?page=2.",
        ),
        retrieve=extend_schema(
            summary=f"One {singular}",
            description="Open to everybody.",
            responses={200: serializer, 404: NOT_FOUND},
        ),
        create=extend_schema(
            summary=f"Create {a} {singular}",
            description=who_writes,
            responses={
                201: serializer,
                400: OpenApiResponse(description="Invalid fields."),
                **write_errors,
            },
        ),
        update=extend_schema(
            summary=f"Replace {a} {singular}",
            description=f"All fields are sent. {who_writes}",
            responses={200: serializer, **write_errors, 404: NOT_FOUND},
        ),
        partial_update=extend_schema(
            summary=f"Change some fields of {a} {singular}",
            description=f"Only the sent fields are changed. {who_writes}",
            responses={200: serializer, **write_errors, 404: NOT_FOUND},
        ),
        destroy=extend_schema(
            summary=f"Delete {a} {singular}",
            description=who_writes,
            responses={
                204: None,
                **write_errors,
                404: NOT_FOUND,
                409: OpenApiResponse(description=protected),
            },
        ),
    )


book_schema = catalog_schema(
    BookSerializer,
    "book",
    "books",
    "Needs the permissions of the user's group: add_book (Editors, Managers), "
    "change_book (Editors, Managers), delete_book (Managers). Changing "
    '"stock" needs inventory.change_stock (Managers), otherwise 403.',
    protected="The book is in orders.",
)
author_schema = catalog_schema(
    AuthorSerializer,
    "author",
    "authors",
    "Staff only (is_staff) with the model permission of the group, like in the admin.",
    protected="The author has books.",
)
category_schema = catalog_schema(
    CategorySerializer,
    "category",
    "categories",
    "Staff only (is_staff) with the model permission of the group (Managers), "
    "like in the admin.",
    protected="The category has books.",
)

order_list_schema = extend_schema_view(
    list=extend_schema(
        summary="List my orders",
        description=(
            "A customer gets own orders, staff gets all. Newest first, "
            "20 per page. Filters: ?status=, ?payment_status=; "
            "?ordering=total | -created_at."
        ),
        responses={200: OrderSerializer(many=True), 401: UNAUTHORIZED},
    ),
    retrieve=extend_schema(
        summary="One order",
        description="Someone else's order is 404 for a customer.",
        responses={200: OrderSerializer, 401: UNAUTHORIZED, 404: NOT_FOUND},
    ),
)

ORDER_CREATE = dict(
    summary="Create an order",
    description=(
        "The delivery data and the books at once (there is no cart in the "
        "API). The prices and the total come from the catalog; the copies "
        'are reserved right away. 400 with "items" when there are not '
        'enough copies: nothing is saved then. Payment: open "site_url" '
        'of the answer, the order page has the "Pay" button.'
    ),
)

IDEMPOTENCY_KEY_PARAMETER = OpenApiParameter(
    name="Idempotency-Key",
    location=OpenApiParameter.HEADER,
    type=str,
    required=False,
    description=(
        "Optional, up to 255 characters, a new one for every new order "
        "(e.g. a UUID). Send the same request with the same key again (a "
        "timeout, a retry) and the answer is the order of the first request, "
        '201 with the header "Idempotent-Replayed: true": no second order. '
        "The same key with other books or another address: 422."
    ),
)

ORDER_CANCEL = dict(
    summary="Cancel my order",
    description=(
        "Only a new unpaid order of the user; the books return to the stock. "
        "Staff can't cancel a customer's order here (403): that is done in the admin."
    ),
)
ORDER_CANCEL_ERRORS = {
    401: UNAUTHORIZED,
    403: FORBIDDEN,
    404: NOT_FOUND,
    409: OpenApiResponse(description="Already cancelled, paid or being processed."),
}

TOKEN_OBTAIN = dict(
    summary="Get a pair of tokens",
    description=(
        'Username and password -> "access" (15 minutes) and "refresh" '
        "(1 day). Send the access token in every request: "
        '"Authorization: Bearer <access>". At most 10 requests per minute '
        "from one address (429)."
    ),
)


def remove_component_descriptions(result, generator, request, public):
    """A postprocessing hook: no developer docstrings in the "Schemas" section.

    drf-spectacular copies the docstring of every serializer into the
    description of its component (BookRequest, Order, ...). Ours explain
    the code ("the order itself is made by the view with create_order()"),
    not the data. The fields and their types stay; the endpoints keep
    their descriptions from extend_schema above.
    Registered in SPECTACULAR_SETTINGS["POSTPROCESSING_HOOKS"].
    """
    for component in result.get("components", {}).get("schemas", {}).values():
        component.pop("description", None)
    return result


TOKEN_REFRESH = dict(
    summary="Get a new access token",
    description="The refresh token -> a new access token, without the password.",
)
TOKEN_VERIFY = dict(
    summary="Check a token",
    description="200 if the token is valid and not expired, otherwise 401.",
)
