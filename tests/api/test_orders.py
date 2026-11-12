"""The orders API: /api/orders/ and /api/orders/<pk>/cancel/.

- a login for everything (JWT or the session);
- a customer sees only own orders, someone else's -> 404;
- staff reads every order, but can't cancel a customer's one (403,
  IsOwnerOrReadOnly);
- an order is created straight with its items (no cart in the API) by
  orders.services.create_order(): the same stock check and reservation
  as the checkout of the site;
- no PUT / PATCH / DELETE.
"""

import threading
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.db import IntegrityError, connection
from rest_framework.test import APIClient

from orders.models import Order
from payments.models import Payment
from tests.factories import BookFactory, OrderFactory, PaymentFactory, UserFactory

pytestmark = pytest.mark.django_db


def order_data(*items, **changes):
    """The body of POST /api/orders/; items = (book, quantity) pairs."""
    data = {
        "full_name": "Ann Shevchenko",
        "phone": "+380 (67) 123-45-67",
        "address": "Kyiv, Khreshchatyk 1",
        "items": [{"book_id": book.pk, "quantity": quantity} for book, quantity in items],
    }
    return {**data, **changes}


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def test_anonymous_gets_401_for_orders(api_client):
    assert api_client.get("/api/orders/").status_code == 401
    assert api_client.post("/api/orders/", {}, format="json").status_code == 401


def test_customer_sees_only_own_orders_with_items(as_user, customer, other_customer):
    book = BookFactory(title="Kobzar", price=Decimal("250.50"))
    own = OrderFactory(user=customer, items=[(book, 2)])
    OrderFactory(user=other_customer, items=[(BookFactory(), 1)])

    response = as_user(customer).get("/api/orders/")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    order = data["results"][0]
    assert order["id"] == own.pk
    assert order["user"] == "ann"
    assert order["status"] == "new"
    assert order["total"] == "501.00"
    assert order["paid_amount"] == "0.00"
    assert order["amount_due"] == "501.00"
    assert order["can_be_cancelled"] is True
    assert order["site_url"] == f"http://testserver/orders/{own.pk}/"
    assert order["items"] == [
        {
            "book": {"id": book.pk, "title": "Kobzar"},
            "title": "Kobzar",
            "price": "250.50",
            "quantity": 2,
            "cost": "501.00",
        }
    ]


def test_someone_elses_order_is_404_for_a_customer(as_user, customer, other_customer):
    foreign = OrderFactory(user=other_customer)

    response = as_user(customer).get(f"/api/orders/{foreign.pk}/")

    # 404, not 403: a customer can't learn that order #pk exists
    assert response.status_code == 404


def test_staff_reads_every_order(as_user, manager, customer, other_customer):
    OrderFactory(user=customer)
    foreign = OrderFactory(user=other_customer)
    client = as_user(manager)

    assert client.get("/api/orders/").json()["count"] == 2
    assert client.get(f"/api/orders/{foreign.pk}/").status_code == 200


def test_paid_amount_counts_only_succeeded_payments(as_user, customer):
    order = OrderFactory(user=customer, items=[(BookFactory(price=Decimal("300")), 1)])
    PaymentFactory(order=order, amount=Decimal("100.00"), status=Payment.Status.SUCCEEDED)
    PaymentFactory(order=order, amount=Decimal("200.00"), status=Payment.Status.FAILED)

    data = as_user(customer).get(f"/api/orders/{order.pk}/").json()

    assert data["paid_amount"] == "100.00"
    assert data["amount_due"] == "200.00"


def test_orders_filter_by_status(as_user, customer):
    OrderFactory(user=customer)
    cancelled = OrderFactory(user=customer, status=Order.Status.CANCELLED)

    data = as_user(customer).get("/api/orders/?status=cancelled").json()

    assert [order["id"] for order in data["results"]] == [cancelled.pk]


def test_order_list_takes_the_same_number_of_queries_for_any_page_size(
    as_user, customer, django_assert_num_queries
):
    for _ in range(10):
        OrderFactory(user=customer, items=[(BookFactory(), 1), (BookFactory(), 2)])
    client = as_user(customer)

    # COUNT + the orders with the users and the paid sums (one JOIN query)
    # + the lines + their books: 4, not a few queries per order
    with django_assert_num_queries(4):
        response = client.get("/api/orders/")

    assert len(response.json()["results"]) == 10


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------


def test_customer_creates_an_order_with_a_jwt_token(
    api_client, customer, get_tokens, mailoutbox, django_capture_on_commit_callbacks
):
    kobzar = BookFactory(title="Kobzar", price=Decimal("250.50"), stock=5)
    other = BookFactory(price=Decimal("100.00"), stock=1)
    access = get_tokens(customer)["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    # execute=True: run the on_commit callbacks (the email after COMMIT)
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            "/api/orders/",
            # The client also sends a price and a total: they are ignored
            {**order_data((kobzar, 2), (other, 1)), "total": "1.00"},
            format="json",
        )

    assert response.status_code == 201
    order = Order.objects.get()
    assert order.user == customer
    # The prices of the catalog: 250.50 * 2 + 100.00
    assert order.total == Decimal("601.00")
    # The phone in the format of the site
    assert order.phone == "+380671234567"
    assert response.json()["id"] == order.pk
    assert len(response.json()["items"]) == 2
    # The copies are reserved
    kobzar.refresh_from_db()
    other.refresh_from_db()
    assert (kobzar.stock, other.stock) == (3, 0)
    # The "order created" email, like after the checkout of the site
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["ann@example.com"]


def test_not_enough_stock_is_400_and_nothing_is_saved(as_user, customer):
    book = BookFactory(title="Kobzar", stock=1)

    response = as_user(customer).post("/api/orders/", order_data((book, 3)), format="json")

    assert response.status_code == 400
    assert "Kobzar" in response.json()["items"][0]
    assert not Order.objects.exists()
    book.refresh_from_db()
    assert book.stock == 1


@pytest.mark.parametrize(
    "change, field",
    [
        ({"items": []}, "items"),
        ({"items": [{"book_id": 999999, "quantity": 1}]}, "items"),
        ({"phone": "call me"}, "phone"),
        ({"full_name": ""}, "full_name"),
    ],
)
def test_invalid_order_is_400(as_user, customer, change, field):
    data = order_data((BookFactory(), 1))

    response = as_user(customer).post("/api/orders/", {**data, **change}, format="json")

    assert response.status_code == 400
    assert field in response.json()
    assert not Order.objects.exists()


@pytest.mark.parametrize("quantities", [(0,), (1, 2)], ids=["quantity 0", "same book twice"])
def test_wrong_lines_are_400(as_user, customer, quantities):
    book = BookFactory()

    response = as_user(customer).post(
        "/api/orders/",
        order_data(*[(book, quantity) for quantity in quantities]),
        format="json",
    )

    assert response.status_code == 400
    assert "items" in response.json()
    assert not Order.objects.exists()


# ---------------------------------------------------------------------------
# Cancelling, and what an order doesn't allow
# ---------------------------------------------------------------------------


def create_order_via_api(client, book, quantity=2):
    response = client.post("/api/orders/", order_data((book, quantity)), format="json")
    assert response.status_code == 201, response.content
    return response.json()["id"]


def test_customer_cancels_a_new_order_and_the_books_return(as_user, customer):
    book = BookFactory(stock=5)
    client = as_user(customer)
    order_id = create_order_via_api(client, book, quantity=2)

    response = client.post(f"/api/orders/{order_id}/cancel/")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["can_be_cancelled"] is False
    book.refresh_from_db()
    assert book.stock == 5


def test_cancel_twice_or_a_paid_order_is_409(as_user, customer):
    client = as_user(customer)
    order_id = create_order_via_api(client, BookFactory(stock=5))
    paid = OrderFactory(user=customer, payment_status=Order.PaymentStatus.PAID)

    client.post(f"/api/orders/{order_id}/cancel/")
    again = client.post(f"/api/orders/{order_id}/cancel/")
    paid_cancel = client.post(f"/api/orders/{paid.pk}/cancel/")

    assert again.status_code == 409
    assert paid_cancel.status_code == 409
    paid.refresh_from_db()
    assert paid.status == Order.Status.NEW


def test_nobody_cancels_someone_elses_order(as_user, customer, other_customer, manager):
    order = OrderFactory(user=customer)

    by_other_customer = as_user(other_customer).post(f"/api/orders/{order.pk}/cancel/")
    by_manager = as_user(manager).post(f"/api/orders/{order.pk}/cancel/")

    # The other customer doesn't see it at all; the manager sees it, but
    # IsOwnerOrReadOnly allows the changes to the owner only
    assert by_other_customer.status_code == 404
    assert by_manager.status_code == 403
    order.refresh_from_db()
    assert order.status == Order.Status.NEW


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_an_order_cannot_be_changed_or_deleted(as_user, customer, method):
    order = OrderFactory(user=customer)

    response = getattr(as_user(customer), method)(
        f"/api/orders/{order.pk}/", {"total": "1.00"}, format="json"
    )

    assert response.status_code == 405
    assert Order.objects.filter(pk=order.pk, total=order.total).exists()


# ---------------------------------------------------------------------------
# Idempotency-Key: a repeated request doesn't create a second order
# ---------------------------------------------------------------------------


def test_the_same_key_twice_gives_the_same_order(
    as_user, customer, mailoutbox, django_capture_on_commit_callbacks
):
    # A client didn't get the answer (timeout) and sends the request again
    book = BookFactory(stock=5)
    client = as_user(customer)
    data = order_data((book, 2))

    with django_capture_on_commit_callbacks(execute=True):
        first = client.post("/api/orders/", data, format="json", HTTP_IDEMPOTENCY_KEY="key-1")
        second = client.post("/api/orders/", data, format="json", HTTP_IDEMPOTENCY_KEY="key-1")

    assert first.status_code == second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert "Idempotent-Replayed" not in first
    assert second["Idempotent-Replayed"] == "true"
    # One order, the copies reserved once, one email
    assert Order.objects.count() == 1
    assert Order.objects.get().idempotency_key == "key-1"
    book.refresh_from_db()
    assert book.stock == 3
    assert len(mailoutbox) == 1


def test_the_same_key_with_another_order_is_422(as_user, customer):
    book = BookFactory(stock=5)
    client = as_user(customer)
    client.post("/api/orders/", order_data((book, 1)), format="json", HTTP_IDEMPOTENCY_KEY="key-1")

    other_quantity = client.post(
        "/api/orders/", order_data((book, 2)), format="json", HTTP_IDEMPOTENCY_KEY="key-1"
    )
    other_address = client.post(
        "/api/orders/",
        order_data((book, 1), address="Lviv, Rynok 1"),
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-1",
    )

    assert other_quantity.status_code == 422
    assert other_address.status_code == 422
    assert Order.objects.count() == 1


def test_the_same_request_is_recognised_after_cleaning(as_user, customer):
    # The phone in another format is the same phone ("+380671234567")
    book = BookFactory(stock=5)
    client = as_user(customer)
    client.post("/api/orders/", order_data((book, 1)), format="json", HTTP_IDEMPOTENCY_KEY="k")

    again = client.post(
        "/api/orders/",
        order_data((book, 1), phone="+380671234567"),
        format="json",
        HTTP_IDEMPOTENCY_KEY="k",
    )

    assert again.status_code == 201
    assert again["Idempotent-Replayed"] == "true"


def test_keys_are_separate_for_every_user(as_user, customer, other_customer):
    book = BookFactory(stock=5)
    data = order_data((book, 1))

    as_user(customer).post("/api/orders/", data, format="json", HTTP_IDEMPOTENCY_KEY="same")
    response = as_user(other_customer).post(
        "/api/orders/", data, format="json", HTTP_IDEMPOTENCY_KEY="same"
    )

    # Not the order of another user: a new one
    assert response.status_code == 201
    assert "Idempotent-Replayed" not in response
    assert Order.objects.count() == 2


def test_a_failed_request_does_not_use_up_the_key(as_user, customer):
    # 400 (not enough copies) saves nothing: the corrected request with the
    # same key creates the order
    book = BookFactory(stock=1)
    client = as_user(customer)

    failed = client.post(
        "/api/orders/", order_data((book, 3)), format="json", HTTP_IDEMPOTENCY_KEY="k"
    )
    fixed = client.post(
        "/api/orders/", order_data((book, 1)), format="json", HTTP_IDEMPOTENCY_KEY="k"
    )

    assert failed.status_code == 400
    assert fixed.status_code == 201
    assert "Idempotent-Replayed" not in fixed


def test_too_long_key_is_400(as_user, customer):
    response = as_user(customer).post(
        "/api/orders/",
        order_data((BookFactory(), 1)),
        format="json",
        HTTP_IDEMPOTENCY_KEY="k" * 256,
    )

    assert response.status_code == 400
    assert "Idempotency-Key" in response.json()
    assert not Order.objects.exists()


def test_parallel_request_with_the_same_key_gets_the_first_order(as_user, customer, monkeypatch):
    # Two requests at the same moment: both look for the key BEFORE the
    # other one has saved its order. Simulated: the first order already
    # exists, but the first lookup of the view misses it, as it would for
    # a request that started before that order was committed.
    from api.views.orders import OrderViewSet

    book = BookFactory(stock=5)
    first = OrderFactory(
        user=customer,
        idempotency_key="k",
        items=[(book, 2)],
        full_name="Ann Shevchenko",
        phone="+380671234567",
        address="Kyiv, Khreshchatyk 1",
    )
    real_lookup = OrderViewSet._order_by_key
    lookups = []

    def lookup_that_misses_once(self, key):
        lookups.append(key)
        return None if len(lookups) == 1 else real_lookup(self, key)

    monkeypatch.setattr(OrderViewSet, "_order_by_key", lookup_that_misses_once)

    response = as_user(customer).post(
        "/api/orders/", order_data((book, 2)), format="json", HTTP_IDEMPOTENCY_KEY="k"
    )

    # create_order() hit the unique constraint, its transaction was rolled
    # back; the second lookup found the first order
    assert lookups == ["k", "k"]
    assert response.status_code == 201
    assert response.json()["id"] == first.pk
    assert response["Idempotent-Replayed"] == "true"
    assert Order.objects.count() == 1
    book.refresh_from_db()
    assert book.stock == 5  # OrderFactory reserves nothing, the rollback returned the 2


def test_other_database_errors_are_not_hidden_as_a_replay(as_user, customer, monkeypatch):
    # IntegrityError without a key (or with a key nobody used) is a real
    # error: it must reach the error log (500), not become an "old order"
    def broken_create_order(*args, **kwargs):
        raise IntegrityError("another constraint")

    monkeypatch.setattr("api.views.orders.create_order", broken_create_order)

    with pytest.raises(IntegrityError):
        as_user(customer).post("/api/orders/", order_data((BookFactory(), 1)), format="json")


# transaction=True: real COMMITs, the two threads see each other's data and
# locks (like test_only_one_of_two_simultaneous_orders_gets_the_last_copy).
# serialized_rollback=True: the groups of the migrations come back after it.
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_simultaneous_requests_with_the_same_key_make_one_order():
    book = BookFactory(stock=5)
    customer = UserFactory(username="ann")
    data = order_data((book, 2))
    # Both threads wait here and send the request at the same moment
    start = threading.Barrier(2)
    answers = []

    def send():
        try:
            client = APIClient()
            client.force_authenticate(customer)
            start.wait()
            response = client.post(
                "/api/orders/", data, format="json", HTTP_IDEMPOTENCY_KEY="same-key"
            )
            replayed = response.has_header("Idempotent-Replayed")
            answers.append((response.status_code, response.json()["id"], replayed))
        finally:
            # Every thread has its own database connection
            connection.close()

    threads = [threading.Thread(target=send) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # Both got 201 with the same order; one of the answers is the replay
    assert [status for status, _, _ in answers] == [201, 201]
    assert answers[0][1] == answers[1][1]
    assert sorted(replayed for _, _, replayed in answers) == [False, True]
    assert Order.objects.count() == 1
    book.refresh_from_db()
    assert book.stock == 3
    assert Group.objects.filter(name="Managers").exists()
