"""Integration: what a customer does from the catalog to a created order.

Every test is a whole flow through the real code: several requests with
one client (the session and the cookies carry over), services,
transactions, emails after COMMIT.

django_capture_on_commit_callbacks(execute=True): a test runs inside a
transaction that is rolled back at the end, so transaction.on_commit()
callbacks (the emails) would never run. Inside this block they are
collected and run when the block ends, as after a real COMMIT.
"""

import threading

import pytest
from django.contrib.auth.models import Group
from django.db import connection
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from inventory.services import set_stock
from orders.models import Order
from orders.services import OrderError, create_order
from payments.models import Payment
from users.models import User

from ..factories import DEFAULT_PASSWORD, BookFactory, UserFactory
from ..helpers import message_levels

pytestmark = pytest.mark.django_db

DELIVERY = {
    "full_name": "Ann Shevchenko",
    "phone": "+380 67 123 45 67",
    "address": "Kyiv, Khreshchatyk 1",
}


def add_to_cart(client, book, quantity=1):
    return client.post(reverse("cart:add", args=[book.pk]), {"quantity": quantity})


def test_guest_cart_survives_login_and_becomes_an_order(
    client, customer, mailoutbox, django_capture_on_commit_callbacks
):
    first = BookFactory(price=100, stock=5)
    second = BookFactory(price=50, stock=5)

    # 1. A guest fills the cart
    add_to_cart(client, first, 2)
    add_to_cart(client, second, 1)

    # 2. Checkout asks to log in; after the login form -> back to checkout
    checkout_url = reverse("orders:checkout")
    assertRedirects(client.get(checkout_url), f"{reverse('users:login')}?next={checkout_url}")
    response = client.post(
        f"{reverse('users:login')}?next={checkout_url}",
        {"username": "ann", "password": DEFAULT_PASSWORD},
    )
    assertRedirects(response, checkout_url)
    assert client.session["cart"] == {
        str(first.pk): {"quantity": 2},
        str(second.pk): {"quantity": 1},
    }

    # 3. The delivery form -> the order
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(checkout_url, DELIVERY)

    order = Order.objects.get(user=customer)
    assertRedirects(response, order.get_absolute_url())
    assert order.total == 250
    assert order.phone == "+380671234567"
    assert {(item.book_id, item.quantity) for item in order.items.all()} == {
        (first.pk, 2),
        (second.pk, 1),
    }
    # Stock reserved, cart empty, one "order created" email to the customer
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.stock, second.stock) == (3, 4)
    assert "cart" not in client.session
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["ann@example.com"]
    assert f"#{order.pk}" in mailoutbox[0].subject
    # The order page offers the "Pay" button
    page = client.get(order.get_absolute_url())
    assert reverse("payments:pay", args=[order.pk]) in page.content.decode()


def test_not_enough_stock_keeps_cart_and_saves_nothing(customer_client, mailoutbox):
    book = BookFactory(stock=3)
    add_to_cart(customer_client, book, 3)
    # Somebody else bought two copies while the customer was filling the form
    set_stock(book, 1)

    response = customer_client.post(reverse("orders:checkout"), DELIVERY)

    assertRedirects(response, reverse("cart:detail"))
    # [-1]: the message of this request; the one from "add to cart" is
    # still unread (redirects are not followed), so it comes first
    assert message_levels(response)[-1] == "error"
    assert not Order.objects.exists()
    book.refresh_from_db()
    assert book.stock == 1
    assert customer_client.session["cart"] == {str(book.pk): {"quantity": 3}}
    assert mailoutbox == []


@pytest.mark.parametrize(("checkbox", "saved"), [("on", True), (None, False)])
def test_checkout_saves_phone_and_address_to_profile_only_when_asked(
    customer, customer_client, checkbox, saved
):
    add_to_cart(customer_client, BookFactory())
    data = {**DELIVERY, "save_to_profile": checkbox} if checkbox else DELIVERY

    customer_client.post(reverse("orders:checkout"), data)

    customer.refresh_from_db()
    assert (customer.phone, customer.address) == (
        ("+380671234567", DELIVERY["address"]) if saved else ("", "")
    )


def test_order_is_created_even_if_email_fails(
    customer_client, failing_mailer, django_capture_on_commit_callbacks
):
    add_to_cart(customer_client, BookFactory())

    with django_capture_on_commit_callbacks(execute=True):
        response = customer_client.post(reverse("orders:checkout"), DELIVERY)

    order = Order.objects.get()
    assertRedirects(response, order.get_absolute_url())
    assert message_levels(response)[-1] == "success"


def test_customer_cancels_order_books_return_and_stripe_page_closes(
    customer_client, fake_stripe, django_capture_on_commit_callbacks
):
    book = BookFactory(stock=5)
    add_to_cart(customer_client, book, 2)
    customer_client.post(reverse("orders:checkout"), DELIVERY)
    order = Order.objects.get()
    # "Pay" opened a Stripe page, the customer came back without paying
    customer_client.post(reverse("payments:pay", args=[order.pk]))
    payment = order.payments.get()

    with django_capture_on_commit_callbacks(execute=True):
        response = customer_client.post(reverse("orders:cancel", args=[order.pk]))

    assertRedirects(response, order.get_absolute_url())
    order.refresh_from_db()
    book.refresh_from_db()
    payment.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert book.stock == 5
    # The open Stripe page was expired: it can't be paid any more
    assert fake_stripe.expired == [payment.external_id]
    assert payment.status == Payment.Status.EXPIRED


def test_sign_up_logs_in_as_customer_then_log_out_and_in_again(client):
    response = client.post(
        reverse("users:signup"),
        {
            "username": "olena",
            "email": "Olena@Example.com",
            "password1": "Very-strong-pass-42",
            "password2": "Very-strong-pass-42",
        },
    )

    assertRedirects(response, reverse("books:list"))
    user = User.objects.get(username="olena")
    assert user.email == "olena@example.com"
    assert list(user.groups.values_list("name", flat=True)) == ["Customers"]
    assert client.get(reverse("users:profile")).status_code == 200  # logged in

    client.post(reverse("users:logout"))
    assert client.get(reverse("users:profile")).status_code == 302  # to the login page

    assert client.login(username="olena", password="Very-strong-pass-42")


# ---------------------------------------------------------------------------
# Two customers buy the last copy at the same moment
# ---------------------------------------------------------------------------


# transaction=True: real COMMITs, so the second thread sees the first one's
# lock and data (a normal test runs in one transaction that is never
# committed). serialized_rollback=True: after the test Django empties the
# tables; this flag puts back what the migrations created (the groups),
# otherwise the tests after this one would find no "Managers" group.
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_only_one_of_two_simultaneous_orders_gets_the_last_copy():
    book = BookFactory(stock=1)
    buyers = [UserFactory(), UserFactory()]
    # Both threads wait here and start create_order() at the same moment
    start = threading.Barrier(len(buyers))
    results = []

    def buy(user):
        try:
            start.wait()
            create_order(
                user, {book.pk: 1}, full_name="Buyer", phone="+380671234567", address="Kyiv"
            )
            results.append("ordered")
        except OrderError:
            results.append("out of stock")
        finally:
            # Every thread has its own database connection; close it, or the
            # test database can't be dropped at the end of the run
            connection.close()

    threads = [threading.Thread(target=buy, args=(user,)) for user in buyers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == ["ordered", "out of stock"]
    book.refresh_from_db()
    assert book.stock == 0
    assert Order.objects.count() == 1
    assert Group.objects.filter(name="Managers").exists()
