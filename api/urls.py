"""URLs of the REST API, included at /api/ (config/urls.py), namespace "api".

    /api/                   the list of sections (DefaultRouter)
    /api/token/             JWT: username + password -> access + refresh
    /api/token/refresh/     JWT: refresh -> a new access
    /api/token/verify/      JWT: is this token valid?
    /api/schema/            OpenAPI schema (YAML; ?format=json for JSON)
    /api/docs/              Swagger UI: the documentation + "Try it out"
    /api/redoc/             ReDoc: the same documentation, for reading

    /api/books/             books: list, create; ?filters, ?search, ?ordering
    /api/books/<pk>/        one book: read, update, delete
    /api/formats/[<pk>/]    formats of the books (paper, e-book, audiobook):
                            price, cover, pages, stock; ?book=<id>
    /api/authors/[<pk>/]    authors, the same actions
    /api/publishers/[<pk>/] publishers, the same actions
    /api/categories/[<pk>/] categories, the same actions
    /api/currencies/[<code>/] the currencies offered, with today's rate
    /api/orders/            my orders (staff: all); POST a new order with items
                            (by format_id; book_id for a book with one format)
    /api/orders/<pk>/       one order
    /api/orders/<pk>/cancel/  POST: cancel my new unpaid order

One register() line of the router gives both URLs of a ViewSet, the list
(/api/books/) and one object (/api/books/<pk>/).
"""

from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter

from .views.auth import (
    DocumentedTokenRefreshView,
    DocumentedTokenVerifyView,
    PublicAPIRootView,
    ThrottledTokenObtainPairView,
)
from .views.catalog import (
    AuthorViewSet,
    BookFormatViewSet,
    BookViewSet,
    CategoryViewSet,
    PublisherViewSet,
)
from .views.currencies import CurrencyViewSet
from .views.orders import OrderViewSet

app_name = "api"


class Router(DefaultRouter):
    # The root page /api/ without a login (see PublicAPIRootView)
    APIRootView = PublicAPIRootView


router = Router()
# register(prefix, ViewSet): /api/books/ and /api/books/<pk>/, URL names
# "api:book-list" and "api:book-detail" (basename from the queryset model)
router.register("books", BookViewSet)
# "api:bookformat-list", "api:bookformat-detail"
router.register("formats", BookFormatViewSet)
router.register("authors", AuthorViewSet)
router.register("publishers", PublisherViewSet)
router.register("categories", CategoryViewSet)
# basename: a ViewSet without a queryset -> "api:currency-list"
router.register("currencies", CurrencyViewSet, basename="currency")
# basename: OrderViewSet has get_queryset() instead of a queryset attribute,
# the router can't take the name from the model -> "api:order-list"
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    path("token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", DocumentedTokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", DocumentedTokenVerifyView.as_view(), name="token_verify"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # url_name: where the page loads the schema from; "api:" because of
    # the namespace of this file
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
    path("redoc/", SpectacularRedocView.as_view(url_name="api:schema"), name="redoc"),
    # The router last: its root pattern is "^$" (/api/ itself)
    *router.urls,
]
