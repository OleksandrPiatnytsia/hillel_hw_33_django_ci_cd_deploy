"""Fixtures shared by all tests (pytest finds this file by its name).

A fixture = a function whose result pytest passes to every test that has
an argument with the same name:

    def test_order_page(customer_client, customer): ...

Fixtures from pytest-django used here and in the tests:
    db            access to the test database (every test in its own
                  transaction, rolled back at the end: no data leaks
                  between tests)
    client        django.test.Client, not logged in
    settings      change a setting for one test, restored afterwards
    mailoutbox    the list of emails "sent" during the test
    django_capture_on_commit_callbacks
                  runs transaction.on_commit() callbacks (emails after
                  COMMIT): in a test the transaction never commits
"""

import smtplib

import pytest
from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.db import connections
from django.core.mail import EmailMessage
from django.test import Client

from payments.providers.stripe_checkout import StripeProvider

from .factories import UserFactory
from .fakes import FakeStripeClient


@pytest.fixture(autouse=True)
def _isolated_environment(settings, tmp_path):
    """For EVERY test (autouse): an empty cache and a temporary media folder.

    - cache: LocMemCache lives as long as the pytest process, so a value
      (or a session) from one test would be seen by the next one;
    - MEDIA_ROOT: covers uploaded by a test go to a temporary folder that
      pytest deletes, not to media/ of the project.
    """
    cache.clear()
    settings.MEDIA_ROOT = tmp_path / "media"
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# Users. Groups "Customers" / "Editors" / "Managers" exist in the test
# database: they are created by the data migration users.0003_create_groups
# (and orders.0002 adds the order permissions to Managers).
# ---------------------------------------------------------------------------


@pytest.fixture
async def async_db_connections():
    """For async tests: close the database connection of the sync_to_async thread.

    The async ORM and `await sync_to_async(Factory)(...)` run the queries in
    one shared worker thread that lives until pytest ends. Its connection
    would stay open, and at the very end pytest-django couldn't drop
    test_bookstore ("is being accessed by other users"). Closed after every
    test, in that same thread (a connection belongs to its thread).
    Used with pytest.mark.usefixtures in the async test modules.
    """
    yield
    await sync_to_async(connections.close_all)()


@pytest.fixture
def customer(db):
    """A customer, as after sign up (group "Customers")."""
    return UserFactory(username="ann", email="ann@example.com", groups=["Customers"])


@pytest.fixture
def other_customer(db):
    """A second customer: "can't see / cancel / pay somebody else's order"."""
    return UserFactory(
        username="bob", email="bob@example.com", first_name="Bob", groups=["Customers"]
    )


@pytest.fixture
def manager(db):
    """A manager: admin access (is_staff) with the rights of the "Managers" group."""
    return UserFactory(username="manager", is_staff=True, groups=["Managers"])


@pytest.fixture
def superuser(db):
    return UserFactory(username="admin", is_staff=True, is_superuser=True)


def _logged_in_client(user):
    # force_login(): a session for the user without the login form and
    # without checking the password: fast, for tests that are not about login
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def customer_client(customer):
    return _logged_in_client(customer)


@pytest.fixture
def other_customer_client(other_customer):
    return _logged_in_client(other_customer)


@pytest.fixture
def manager_client(manager):
    return _logged_in_client(manager)


@pytest.fixture
def superuser_client(superuser):
    return _logged_in_client(superuser)


# ---------------------------------------------------------------------------
# External services
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_stripe(monkeypatch):
    """Stripe without the network: StripeProvider uses a FakeStripeClient.

    monkeypatch replaces the method only for this test and puts the real
    one back afterwards.
    """
    client = FakeStripeClient()
    monkeypatch.setattr(StripeProvider, "_client", lambda self: client)
    return client


@pytest.fixture
def failing_mailer(monkeypatch):
    """Every email fails as if Gmail was down (SMTPException on send()).

    EmailMultiAlternatives (orders/emails.py) inherits send() from
    EmailMessage, so patching EmailMessage covers every email.
    """

    def broken_send(self, fail_silently=False):
        raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed (test)")

    monkeypatch.setattr(EmailMessage, "send", broken_send)
