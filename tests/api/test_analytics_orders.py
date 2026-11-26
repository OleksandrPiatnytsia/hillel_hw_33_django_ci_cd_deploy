"""GET /api/analytics/orders/: the orders for the backfill of Analytics.

The answer is what the command backfill_orders of Analytics reads
(sales/backfill.py there): {"next", "previous", "results": [{"order",
"updated_at", "paid_at", "cancelled_at"}]}, the cursor taken from "next".
"""

import json
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from orders.models import Order
from outbox.models import OutboxEvent
from outbox.services import record_event
from outbox.snapshot import order_snapshot

from ..factories import BookFactory, OrderFactory, UserFactory

pytestmark = pytest.mark.django_db

URL = "/api/analytics/orders/"


@pytest.fixture
def service(db):
    """The account of Analytics: group Services (users/0008), not staff."""
    return UserFactory(username="analytics-service", groups=["Services"])


@pytest.fixture
def books(db):
    return BookFactory(title="Kobzar"), BookFactory(title="Zakhar Berkut")


def make_order(books, created_at=None, **fields):
    order = OrderFactory(items=[(books[0], 2), (books[1], 1)], **fields)
    if created_at:
        Order.objects.filter(pk=order.pk).update(created_at=created_at)
        order.refresh_from_db()
    return order


def cursor_of(next_url):
    return parse_qs(urlsplit(next_url).query)["cursor"][0]


# --- Who ---------------------------------------------------------------------


# Generated with AI
def test_without_a_token_401(api_client):
    assert api_client.get(URL).status_code == 401


# Generated with AI
@pytest.mark.parametrize("groups, staff", [(["Customers"], False), (["Managers"], True)])
def test_other_accounts_403(as_user, groups, staff):
    # A manager sees every order in the admin, but this export is the
    # service's: its own permission, not is_staff
    user = UserFactory(groups=groups, is_staff=staff)

    assert as_user(user).get(URL).status_code == 403


# Generated with AI
def test_the_service_logs_in_with_a_jwt(api_client, get_tokens, service, books):
    make_order(books)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {get_tokens(service)['access']}")

    response = api_client.get(URL)

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1


# --- What ----------------------------------------------------------------------


# Generated with AI
def test_an_item_is_the_snapshot_of_the_events(as_user, service, books):
    order = make_order(books)

    item = as_user(service).get(URL).json()["results"][0]

    # The same function as the events: Analytics stores it with the same code
    assert item["order"] == json.loads(json.dumps(order_snapshot(order)))
    assert item["order"]["items"][0]["book"]["title"] == "Kobzar"
    assert item["updated_at"] == order.updated_at.isoformat().replace("+00:00", "Z")
    assert (item["paid_at"], item["cancelled_at"]) == (None, None)


# Generated with AI
def test_no_personal_data_in_the_answer(as_user, service, books):
    customer = UserFactory(email="ann@example.com", phone="+380501112233")
    make_order(books, user=customer)

    text = as_user(service).get(URL).content.decode()

    for private in ["Ann Shevchenko", "+380671234567", "Khreshchatyk", "ann@example.com"]:
        assert private not in text
    assert f'"user": {customer.pk}' not in text


# Generated with AI
def test_paid_and_cancelled_moments_come_from_the_outbox(as_user, service, books):
    paid = make_order(books, payment_status=Order.PaymentStatus.PAID)
    cancelled = make_order(books, status=Order.Status.CANCELLED)
    paid_event = record_event(paid, OutboxEvent.Type.ORDER_PAID)
    cancelled_event = record_event(cancelled, OutboxEvent.Type.ORDER_CANCELLED)
    # An older order without events (before version 1.5.0): null, Analytics
    # takes updated_at
    old_paid = make_order(books, payment_status=Order.PaymentStatus.PAID)

    results = {item["order"]["id"]: item for item in as_user(service).get(URL).json()["results"]}

    def iso(moment):
        return moment.isoformat().replace("+00:00", "Z")

    assert results[paid.pk]["paid_at"] == iso(paid_event.created_at)
    assert results[paid.pk]["cancelled_at"] is None
    assert results[cancelled.pk]["cancelled_at"] == iso(cancelled_event.created_at)
    assert results[old_paid.pk]["paid_at"] is None


# Generated with AI
def test_orders_without_items_are_skipped(as_user, service, books):
    make_order(books)
    OrderFactory()  # no items

    assert len(as_user(service).get(URL).json()["results"]) == 1


# --- Pages ---------------------------------------------------------------------


# Generated with AI
def test_pages_by_a_cursor_oldest_first(as_user, service, books):
    orders = [make_order(books) for _ in range(5)]
    client = as_user(service)

    first = client.get(URL, {"page_size": 2}).json()
    second = client.get(URL, {"page_size": 2, "cursor": cursor_of(first["next"])}).json()
    third = client.get(URL, {"page_size": 2, "cursor": cursor_of(second["next"])}).json()

    ids = [item["order"]["id"] for page in (first, second, third) for item in page["results"]]
    assert ids == [order.pk for order in orders]
    assert third["next"] is None


# Generated with AI
def test_a_new_order_during_the_backfill_is_not_skipped_or_repeated(as_user, service, books):
    first_orders = [make_order(books) for _ in range(3)]
    client = as_user(service)
    first = client.get(URL, {"page_size": 2}).json()

    newest = make_order(books)  # created between the two pages
    second = client.get(URL, {"page_size": 2, "cursor": cursor_of(first["next"])}).json()

    # "After id N", not "page 2": nothing skipped, nothing twice
    assert [item["order"]["id"] for item in first["results"]] == [o.pk for o in first_orders[:2]]
    assert [item["order"]["id"] for item in second["results"]] == [first_orders[2].pk, newest.pk]


# Generated with AI
def test_page_size_default_and_maximum(as_user, service, books):
    from api.views.analytics import AnalyticsOrdersPagination

    assert (AnalyticsOrdersPagination.page_size, AnalyticsOrdersPagination.max_page_size) == (
        100,
        500,
    )
    make_order(books)
    # More than the maximum is cut to it, not refused
    assert as_user(service).get(URL, {"page_size": 10_000}).status_code == 200


# Generated with AI
def test_the_number_of_queries_does_not_grow_with_the_orders(as_user, service, books):
    client = as_user(service)
    make_order(books)
    client.get(URL)  # the first request also reads the rights of the user
    with CaptureQueriesContext(connection) as one_order:
        client.get(URL)
    for _ in range(9):
        make_order(books)

    with CaptureQueriesContext(connection) as ten_orders:
        response = client.get(URL)

    assert len(response.json()["results"]) == 10
    assert len(ten_orders) == len(one_order)


# --- Filters -------------------------------------------------------------------


# Generated with AI
def test_created_from_and_to_are_whole_utc_days(as_user, service, books):
    def at(day, hour, minute=0, second=0):
        return timezone.make_aware(datetime(2026, 11, day, hour, minute, second))

    make_order(books, created_at=at(9, 23, 59, 59))  # the day before
    inside = [
        make_order(books, created_at=at(10, 0)),
        make_order(books, created_at=at(11, 23, 59, 59)),
    ]
    make_order(books, created_at=at(12, 0))  # the day after

    results = (
        as_user(service)
        .get(URL, {"created_from": "2026-11-10", "created_to": "2026-11-11"})
        .json()["results"]
    )

    assert [item["order"]["id"] for item in results] == [order.pk for order in inside]


# Generated with AI
def test_only_one_end_of_the_period(as_user, service, books):
    old = make_order(books, created_at=timezone.now() - timedelta(days=40))
    new = make_order(books)
    client = as_user(service)
    since = (timezone.now() - timedelta(days=1)).date().isoformat()

    after = client.get(URL, {"created_from": since}).json()["results"]
    before = client.get(URL, {"created_to": since}).json()["results"]

    assert [item["order"]["id"] for item in after] == [new.pk]
    assert [item["order"]["id"] for item in before] == [old.pk]


# Generated with AI
@pytest.mark.parametrize(
    "params, field",
    [
        ({"created_from": "2026-13-01"}, "created_from"),
        ({"created_to": "yesterday"}, "created_to"),
        ({"created_from": "2026-11-30", "created_to": "2026-11-01"}, "non_field_errors"),
    ],
)
def test_wrong_dates_400(as_user, service, params, field):
    response = as_user(service).get(URL, params)

    assert response.status_code == 400
    assert field in response.json()


# --- Documentation and logs ------------------------------------------------


# Generated with AI
def test_in_the_swagger_schema(api_client):
    schema = api_client.get("/api/schema/", {"format": "json"}).json()

    operation = schema["paths"][URL]["get"]
    assert operation["tags"] == ["analytics"]
    parameters = {parameter["name"] for parameter in operation["parameters"]}
    assert {"created_from", "created_to", "cursor", "page_size"} <= parameters


# Generated with AI
def test_every_page_is_logged(as_user, service, books, caplog):
    make_order(books)

    with caplog.at_level("INFO", "api.views.analytics"):
        as_user(service).get(URL, {"created_from": "2026-01-01"})

    assert "user=analytics-service created_from=2026-01-01 created_to=- orders=1" in caplog.text
