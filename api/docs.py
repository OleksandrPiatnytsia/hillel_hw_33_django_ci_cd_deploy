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

from .serializers.catalog import (
    AuthorSerializer,
    BookFormatSerializer,
    BookSerializer,
    CategorySerializer,
    PublisherSerializer,
)
from .serializers.currencies import CurrencySerializer
from .serializers.orders import OrderSerializer

# Common answers, reused by several endpoints
UNAUTHORIZED = OpenApiResponse(description="No valid token or session (401).")
FORBIDDEN = OpenApiResponse(description="Logged in, but not allowed (403).")
NOT_FOUND = OpenApiResponse(description="No such object (404).")


def catalog_schema(serializer, singular, plural, who_writes, *, protected, read_parameters=()):
    """extend_schema_view for a catalog ViewSet: the 6 actions of a ModelViewSet.

    serializer: the answer of the actions (responses= replaces the default
    one, so it is given again; None there would mean "no body");
    singular / plural: "book" / "books"; who_writes: one sentence on the
    permissions; protected: when DELETE answers 409; read_parameters: extra
    query parameters of list and retrieve (?currency= of the books).
    """
    write_errors = {401: UNAUTHORIZED, 403: FORBIDDEN}
    # "a book", "an author"
    a = "an" if singular[0] in "aeiou" else "a"
    return extend_schema_view(
        list=extend_schema(
            summary=f"List {plural}",
            description=f"Open to everybody. 20 {plural} per page: ?page=2.",
            parameters=list(read_parameters),
        ),
        retrieve=extend_schema(
            summary=f"One {singular}",
            description="Open to everybody.",
            parameters=list(read_parameters),
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


# ?currency= of the books list and of one book
CURRENCY_PARAMETER = OpenApiParameter(
    name="currency",
    type=str,
    required=False,
    description=(
        'A code from /api/currencies/ ("USD", "EUR"; "UAH" by default): '
        '"display_price" of every book (the cheapest format on sale) and of '
        "every format in it, converted at today's NBU rate. ?price_min=, "
        "?price_max= and ?ordering=price of the books use this price too, so "
        "formats priced in different currencies are compared correctly. "
        "A code that is not offered: 400."
    ),
)
book_schema = catalog_schema(
    BookSerializer,
    "book",
    "books",
    "Needs the permissions of the user's group: add_book (Editors, Managers), "
    "change_book (Editors, Managers), delete_book (Managers). The prices, "
    "types, covers, pages and stock belong to the formats of the book: "
    '"formats" lists the ones on sale, /api/formats/ writes them. A new '
    "book is not on sale until its first format is added.",
    protected="The book is in orders.",
    read_parameters=[CURRENCY_PARAMETER],
)
format_schema = catalog_schema(
    BookFormatSerializer,
    "format",
    "formats",
    "One way to buy a book: paper, e-book or audiobook, each with its own price "
    '("format_type" and "book_id" are set only when the format is created). '
    '"cover_type" only for paper, "pages" not for an audiobook, one format of '
    "a type per book. Needs the permissions of the user's group: "
    "add_bookformat, change_bookformat, delete_bookformat (Editors, Managers). "
    'Changing "stock" (paper only; null for a file) needs '
    "inventory.change_stock (Managers), otherwise 403. Turned off formats "
    "(is_active: false) are listed only for users who may change them.",
    protected=(
        "The format is in orders, or it is the last format of the book: "
        'turn it off instead ("is_active": false).'
    ),
    read_parameters=[CURRENCY_PARAMETER],
)
currency_schema = extend_schema_view(
    list=extend_schema(
        summary="List currencies",
        description=(
            "Open to everybody. The currencies the shop offers (UAH first) "
            'with today\'s NBU rate: "rate" UAH for 1 unit, "rate_date" the '
            'day of that rate (null for UAH). Use a "code" in '
            "/api/books/?currency= and in a new order."
        ),
        responses={200: CurrencySerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="One currency",
        description="Open to everybody. 404 for a currency that is not offered.",
        responses={200: CurrencySerializer, 404: NOT_FOUND},
    ),
)

author_schema = catalog_schema(
    AuthorSerializer,
    "author",
    "authors",
    "Staff only (is_staff) with the model permission of the group, like in the admin.",
    protected="The author has books.",
)
publisher_schema = catalog_schema(
    PublisherSerializer,
    "publisher",
    "publishers",
    "Staff only (is_staff) with the model permission of the group, like in the admin.",
    protected="The publisher has books.",
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
            "20 per page. Filters: ?status=, ?payment_status=, ?currency=; "
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
        "API). Every line names a format: "
        '{"format_id": 12, "quantity": 2} (the formats are in "formats" of '
        'a book). {"book_id": 7, "quantity": 2} is accepted for a book with '
        'one format on sale; with several it is 400: send "format_id". '
        "The prices and the total come from the catalog; the copies of a "
        "paper format are reserved right away (an e-book or an audiobook "
        'has no copies). "currency": a code from /api/currencies/ '
        '("UAH" by default); every format is converted into it at today\'s '
        'NBU rate and the order keeps that rate. 400 with "items" when there '
        "are not enough copies: nothing is saved then. Payment: open "
        '"site_url" of the answer, the order page has the "Pay" button '
        "(in the order currency)."
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
        "The same key with other formats or another address: 422."
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
