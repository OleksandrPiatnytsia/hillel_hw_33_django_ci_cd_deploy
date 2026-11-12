"""Sentry (config/sentry.py): what is sent, what is not.

No real sentry.io: the "sent" events are kept in memory by a fake transport.
"""

import json

import pytest
import sentry_sdk
from asgiref.sync import async_to_sync
from asgiref.testing import ApplicationCommunicator
from django.test import Client
from django.urls import reverse
from sentry_sdk.transport import Transport

from config.sentry import before_breadcrumb, init_sentry, make_traces_sampler

from ..factories import UserFactory

# A DSN of the right format; nothing is ever sent to it (MemoryTransport)
FAKE_DSN = "https://public@o0.ingest.sentry.invalid/1"


class MemoryTransport(Transport):
    """Keeps the envelopes instead of sending them over the network."""

    def __init__(self, options=None):
        super().__init__(options)
        self.events = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type == "event":
                self.events.append(item.payload.json)


@pytest.fixture
def sentry_events():
    """Sentry on, with the memory transport; off again after the test."""
    transport = MemoryTransport()
    init_sentry(FAKE_DSN, environment="test", transport=transport)
    yield transport.events
    sentry_sdk.get_client().close()
    sentry_sdk.init()  # no DSN: a client that sends nothing


# Generated with AI
def test_without_dsn_sentry_is_not_started(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda *args, **kwargs: calls.append(kwargs))

    assert init_sentry("") is False
    assert calls == []


async def asgi_get(path, headers):
    """One GET through config.asgi.application, the app gunicorn runs.

    Not django.test.Client: it skips the ASGI handler, and the Sentry SDK
    reads the request data exactly there.
    """
    from config.asgi import application

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": headers,
        "client": ("203.0.113.7", 50000),
        "server": ("testserver", 80),
    }
    communicator = ApplicationCommunicator(application, scope)
    await communicator.send_input({"type": "http.request", "body": b""})
    start = await communicator.receive_output(timeout=5)
    await communicator.receive_output(timeout=5)  # the body
    return start["status"]


# Generated with AI
@pytest.mark.django_db(transaction=True)  # the ASGI handler uses its own connection
def test_view_error_is_sent_without_personal_data(sentry_events):
    admin = UserFactory(is_superuser=True, is_staff=True, email="boss@example.com")
    client = Client()
    client.force_login(admin)
    session_id = client.cookies["sessionid"].value
    headers = [
        (b"host", b"testserver"),
        (b"cookie", f"sessionid={session_id}; django_language=uk".encode()),
        (b"x-forwarded-for", b"198.51.100.9"),
        (b"user-agent", b"pytest"),
    ]

    status = async_to_sync(asgi_get)("/sentry-debug/", headers)
    sentry_sdk.flush()

    assert status == 500  # the user sees templates/500.html
    [event] = sentry_events
    assert event["exception"]["values"][-1]["type"] == "ZeroDivisionError"
    assert event["environment"] == "test"
    request = event["request"]
    assert request["url"] == "http://testserver/sentry-debug/"
    assert request["headers"]["user-agent"] == "pytest"  # useful headers stay
    assert "cookies" not in request  # none at all, not even the language
    # data_collection: no session id (it would let anyone log in as this
    # user), no IP address, no email anywhere in what Sentry receives
    sent = json.dumps(event)
    for private in (session_id, "198.51.100.9", "203.0.113.7", "boss@example.com"):
        assert private not in sent


# Generated with AI
@pytest.mark.django_db
@pytest.mark.parametrize("is_superuser", [False, None])  # a customer, anonymous
def test_sentry_debug_is_404_for_everyone_else(client, is_superuser):
    if is_superuser is not None:
        client.force_login(UserFactory())

    assert client.get(reverse("sentry_debug")).status_code == 404


# Generated with AI
def test_health_checks_are_never_timed():
    sampler = make_traces_sampler(0.5)

    assert sampler({"asgi_scope": {"path": "/health/"}}) == 0.0
    assert sampler({"wsgi_environ": {"PATH_INFO": "/health/"}}) == 0.0
    assert sampler({"asgi_scope": {"path": "/books/1/"}}) == 0.5
    assert sampler({}) == 0.5  # a Celery task


# Generated with AI
def test_task_follows_the_decision_of_the_request_that_queued_it():
    sampler = make_traces_sampler(0.1)

    assert sampler({"parent_sampled": True}) == 1.0
    assert sampler({"parent_sampled": False}) == 0.0


# Generated with AI
def test_log_lines_with_ip_addresses_are_not_breadcrumbs():
    assert (
        before_breadcrumb({"category": "users.signals", "message": "Login: ip=1.2.3.4"}, {}) is None
    )
    crumb = {"category": "orders", "message": "Order #1 cancelled"}
    assert before_breadcrumb(crumb, {}) is crumb
