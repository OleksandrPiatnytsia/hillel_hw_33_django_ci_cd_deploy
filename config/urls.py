import re

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from config.views import health, sentry_debug, serve_media, set_language

urlpatterns = [
    path("admin/", admin.site.urls),
    # 200 / 503: are PostgreSQL and Redis reachable (docker-compose healthcheck)
    path("health/", health, name="health"),
    # Superuser only: raises an error to check Sentry (404 for anyone else)
    path("sentry-debug/", sentry_debug, name="sentry_debug"),
    # The language switcher (navbar): POST -> cookie + User.language -> back.
    # The same name as Django's view: {% url 'set_language' %}
    path("i18n/setlang/", set_language, name="set_language"),
    # Login / logout / sign up: /accounts/login/, ... (namespace "users")
    path("accounts/", include("users.urls")),
    # Session cart: /cart/, /cart/add/<book_id>/, ... (namespace "cart")
    path("cart/", include("cart.urls")),
    # Checkout and the user's orders: /orders/checkout/, /orders/<pk>/, ...
    path("orders/", include("orders.urls")),
    # "Pay" button and Stripe's return pages: /payments/pay/<order_id>/, ...
    path("payments/", include("payments.urls")),
    # REST API: tokens, docs, the catalog and the orders (namespace "api").
    # Before the catalog: books.urls is included at "" and must not get
    # the first chance at /api/...
    path("api/", include("api.urls")),
    # "Log in" / "Log out" in the top right corner of the browsable API
    # (the HTML pages of /api/... in a browser). A separate include: the
    # templates of DRF look for the namespace "rest_framework" exactly,
    # inside "api" it would be "api:rest_framework".
    path("api/auth/", include("rest_framework.urls")),
    # Uploaded covers: /media/covers/2026/11/kobzar.jpg. Served by Django
    # with runserver (DEBUG) and on Railway (DJANGO_SERVE_MEDIA=True); in
    # local Docker nginx answers /media/ before the request gets here.
    # Before the catalog: its patterns start at the site root too.
    re_path(
        rf"^{re.escape(settings.MEDIA_URL.lstrip('/'))}(?P<path>.+)$",
        serve_media,
        name="media",
    ),
    # Bookstore catalog lives at the site root; namespace "books" comes
    # from app_name in books/urls.py
    path("", include("books.urls")),
]

if settings.ENABLE_DEBUG_TOOLBAR:
    # Imported here: without requirements-dev.txt the package doesn't exist.
    # /__debug__/... — the toolbar loads its panels from these URLs.
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()
