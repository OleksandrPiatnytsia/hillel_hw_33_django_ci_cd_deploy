"""Unit tests of the async views and the async path of the middleware.

AsyncClient sends the request through Django's ASGI handler, like
gunicorn + uvicorn in Docker: async views are awaited in the event loop,
the middleware chain runs in async mode (RequestTimingMiddleware.__acall__).

Why transaction=True: the async ORM runs the queries in a worker thread
(sync_to_async), and a thread has its own database connection. A normal
test keeps its data in an open transaction of the MAIN connection, which
the worker thread can't see. With transaction=True the test data is really
committed (and the tables are emptied after the test).
serialized_rollback=True: after emptying, Django puts back the data of the
migrations (the "Managers" group, permissions, content types), so the
next tests still find it.

Sync helpers in async tests: factories and other ORM code are sync, so they
are called through sync_to_async (a direct call raises
SynchronousOnlyOperation inside the event loop).
"""

import asyncio
from decimal import Decimal

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.test import AsyncClient
from django.urls import reverse

from config import views as config_views
from orders.models import Order
from payments.models import Payment

from ..factories import BookFactory, OrderFactory, PaymentFactory, UserFactory

pytestmark = [
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
    pytest.mark.usefixtures("async_db_connections"),
]

COOKIE = settings.LANGUAGE_COOKIE_NAME


# ---------------------------------------------------------------------------
# /health/
# ---------------------------------------------------------------------------


async def test_health_async_ok():
    response = await AsyncClient().get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "cache": "ok"}
    # RequestTimingMiddleware worked in async mode too
    assert response["X-Request-Duration"].endswith("ms")


async def test_health_async_database_down(monkeypatch):
    async def broken_database():
        raise ConnectionError("PostgreSQL is down (test)")

    monkeypatch.setitem(config_views.CHECKS, "database", broken_database)

    response = await AsyncClient().get(reverse("health"))

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "error", "cache": "ok"}


async def test_cache_checks_at_the_same_moment_dont_disturb_each_other():
    """Under ASGI many /health/ requests run at once in one process. With
    one shared cache key they overwrote each other's value (a healthy
    cache answered 503: found by a load test with 50 parallel requests)."""
    await asyncio.gather(*(config_views.check_cache() for _ in range(30)))  # no error

    assert not await cache.ahas_key("health_check")  # the keys were removed


async def test_health_accepts_only_get():
    assert (await AsyncClient().post(reverse("health"))).status_code == 405


# ---------------------------------------------------------------------------
# /search/?q=
# ---------------------------------------------------------------------------


async def test_book_search_finds_by_title_and_author():
    await sync_to_async(BookFactory)(title="Kobzar", author__name="Taras Shevchenko")
    await sync_to_async(BookFactory)(title="Zakhar Berkut", author__name="Ivan Franko")
    await sync_to_async(BookFactory)(title="Lisova pisnia", author__name="Lesya Ukrainka", stock=0)

    by_title = await AsyncClient().get(reverse("books:search"), {"q": "kobz"})
    by_author = await AsyncClient().get(reverse("books:search"), {"q": "FRANKO"})

    assert [book["title"] for book in by_title.json()["results"]] == ["Kobzar"]
    assert by_title.json()["results"][0]["author"] == "Taras Shevchenko"
    assert by_title.json()["results"][0]["url"].startswith("/")
    assert [book["title"] for book in by_author.json()["results"]] == ["Zakhar Berkut"]


@pytest.mark.parametrize("query", ["", "k", "  k  "])
async def test_book_search_needs_two_letters(query):
    await sync_to_async(BookFactory)(title="Kobzar")

    response = await AsyncClient().get(reverse("books:search"), {"q": query})

    assert response.json() == {"results": []}


async def test_book_search_returns_at_most_eight_sorted_by_title():
    for number in range(12):
        await sync_to_async(BookFactory)(title=f"Poems {number:02}")

    response = await AsyncClient().get(reverse("books:search"), {"q": "poems"})

    titles = [book["title"] for book in response.json()["results"]]
    assert titles == [f"Poems {number:02}" for number in range(8)]


@pytest.mark.parametrize(("language", "price"), [("uk", "250,50"), ("en", "250.50")])
async def test_book_search_price_in_the_language_of_the_request(language, price):
    await sync_to_async(BookFactory)(title="Kobzar", price=Decimal("250.50"))
    client = AsyncClient()
    client.cookies[COOKIE] = language

    response = await client.get(reverse("books:search"), {"q": "kobzar"})

    assert response.json()["results"][0]["price"] == price


# ---------------------------------------------------------------------------
# /orders/<pk>/status/
# ---------------------------------------------------------------------------


@pytest.fixture
def order_of_ann():
    """A 300 UAH order of "ann" with a succeeded payment of 100 UAH (sync fixture)."""
    user = UserFactory(username="ann")
    order = OrderFactory(user=user, total=Decimal("300.00"))
    PaymentFactory(order=order, amount=Decimal("100.00"), status=Payment.Status.SUCCEEDED)
    PaymentFactory(order=order, amount=Decimal("200.00"), status=Payment.Status.PENDING)
    order.refresh_payment_status()
    return order


async def test_order_status_needs_login(order_of_ann):
    response = await AsyncClient().get(reverse("orders:status", args=[order_of_ann.pk]))

    assert response.status_code == 401
    assert response.json() == {"error": "login required"}


async def test_order_status_of_someone_else_is_404(order_of_ann):
    client = AsyncClient()
    await client.aforce_login(await sync_to_async(UserFactory)(username="bob"))

    response = await client.get(reverse("orders:status", args=[order_of_ann.pk]))

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "uk",
            {
                "status_display": "Нове",
                "payment_status_display": "Частково оплачено",
                "paid_amount": "100,00",
                "amount_due": "200,00",
            },
        ),
        (
            "en",
            {
                "status_display": "New",
                "payment_status_display": "Partially paid",
                "paid_amount": "100.00",
                "amount_due": "200.00",
            },
        ),
    ],
)
async def test_order_status_json(order_of_ann, language, expected):
    client = AsyncClient()
    client.cookies[COOKIE] = language
    await client.aforce_login(order_of_ann.user)

    response = await client.get(reverse("orders:status", args=[order_of_ann.pk]))

    assert response.status_code == 200
    assert response["Cache-Control"].startswith("max-age=0")  # never_cache
    assert response.json() == {
        "id": order_of_ann.pk,
        "status": Order.Status.NEW,
        "payment_status": Order.PaymentStatus.PARTIALLY_PAID,
        **expected,
    }


async def test_order_status_without_payments_is_zero_paid():
    """AI review (AI_REVIEW.md, order_status): the sum of the payments now
    comes from the same query as the order; no payments -> SUM is NULL."""
    order = await sync_to_async(OrderFactory)(total=Decimal("300.00"))
    client = AsyncClient()
    await client.aforce_login(order.user)  # cached by the factory, no query

    response = await client.get(reverse("orders:status", args=[order.pk]))

    assert response.json()["payment_status"] == Order.PaymentStatus.UNPAID
    assert response.json()["paid_amount"] == "0,00"  # default language: uk
    assert response.json()["amount_due"] == "300,00"
