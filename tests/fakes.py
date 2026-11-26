"""Fakes of external services: Stripe and Analytics without the network.

FakeStripeClient replaces stripe.StripeClient (StripeProvider._client(),
the `fake_stripe` fixture in conftest.py). It has the same three calls the
project uses and keeps the sessions in a dict:

    client.v1.checkout.sessions.create(params=..., options=...)
    client.v1.checkout.sessions.retrieve(session_id)
    client.v1.checkout.sessions.expire(session_id)

A test plays "the customer" with fake_stripe.pay(session_id) /
fake_stripe.expire_session(session_id), and checks what the site sent with
fake_stripe.created (the params of every create() call).
fake_stripe.fail_with = stripe.APIConnectionError("...") -> every next call
raises it (Stripe is down).

Why a fake object and not unittest.mock.MagicMock: a MagicMock answers any
call, even a mistyped one (sesions.create), and the test still passes; the
fake has only the real names, and keeps state between calls (create ->
pay -> retrieve), so whole flows can be tested.

stripe_webhook_headers(): the "Stripe-Signature" header for a test webhook
request. The REAL check (stripe.Webhook.construct_event) runs against it,
not a mock: a wrong signature in the code would fail the test.
"""

import hashlib
import hmac
import itertools
import json
import time
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urlsplit

import stripe
from django.conf import settings

# Every session the fakes created: id -> session. stripe_event_payload()
# reads the amount and the currency from here, as the real Stripe puts the
# session (with them) into the event.
CREATED_SESSIONS = {}


class _FakeSessions:
    """client.v1.checkout.sessions"""

    def __init__(self, client):
        self._client = client

    def create(self, params, options=None):
        self._client._check_failure()
        number = next(self._client._numbers)
        price = params["line_items"][0]["price_data"]
        session = SimpleNamespace(
            id=f"cs_test_fake_{number}",
            url=f"https://checkout.stripe.test/pay/cs_test_fake_{number}",
            # open | complete | expired, and unpaid | paid (Stripe's names)
            status="open",
            payment_status="unpaid",
            expires_at=params["expires_at"],
            metadata=params.get("metadata", {}),
            # The sum of the line items, in the minor units, as Stripe has it
            amount_total=price["unit_amount"] * params["line_items"][0]["quantity"],
            currency=price["currency"],
        )
        self._client.sessions[session.id] = session
        CREATED_SESSIONS[session.id] = session
        self._client.created.append({"params": params, "options": options or {}})
        return session

    def retrieve(self, session_id):
        self._client._check_failure()
        return self._client._get(session_id)

    def expire(self, session_id):
        self._client._check_failure()
        session = self._client._get(session_id)
        if session.status != "open":
            # The real Stripe answers 400 for a session that is not open
            raise stripe.InvalidRequestError(
                f"Only open sessions can be expired: {session_id}", "session"
            )
        session.status = "expired"
        self._client.expired.append(session_id)
        return session


class FakeStripeClient:
    def __init__(self):
        self.sessions = {}  # id -> session
        self.created = []  # params of every create(), in order
        self.expired = []  # ids passed to expire() that were open
        self.fail_with = None  # a stripe.StripeError to raise on every call
        self._numbers = itertools.count(1)
        self.v1 = SimpleNamespace(checkout=SimpleNamespace(sessions=_FakeSessions(self)))

    # ------------------------------------------------------------------
    # What the customer does on the Stripe page
    # ------------------------------------------------------------------

    def pay(self, session_id):
        session = self._get(session_id)
        session.status = "complete"
        session.payment_status = "paid"
        return session

    def expire_session(self, session_id):
        """The page timed out by itself (not through the API)."""
        session = self._get(session_id)
        session.status = "expired"
        return session

    # ------------------------------------------------------------------

    def _get(self, session_id):
        try:
            return self.sessions[session_id]
        except KeyError:
            raise stripe.InvalidRequestError(
                f"No such checkout.session: {session_id}", "id"
            ) from None

    def _check_failure(self):
        if self.fail_with is not None:
            raise self.fail_with


# ---------------------------------------------------------------------------
# Webhook requests
# ---------------------------------------------------------------------------

_event_numbers = itertools.count(1)


def stripe_event_payload(
    event_type,
    session_id,
    *,
    payment_status="paid",
    status="complete",
    amount_total=None,
    currency=None,
):
    """JSON body of a Stripe event about one Checkout Session, as text.

    amount_total, currency: by default those of the session created by
    FakeStripeClient (what Stripe sends); given -> a session changed on
    Stripe's side.
    """
    created = CREATED_SESSIONS.get(session_id)
    if amount_total is None and created is not None:
        amount_total = created.amount_total
    if currency is None and created is not None:
        currency = created.currency
    return json.dumps(
        {
            "id": f"evt_test_{next(_event_numbers)}",
            "object": "event",
            "type": event_type,
            "data": {
                "object": {
                    "id": session_id,
                    "object": "checkout.session",
                    "status": status,
                    "payment_status": payment_status,
                    "amount_total": amount_total,
                    "currency": currency,
                }
            },
        }
    )


def stripe_webhook_headers(payload, *, secret=None, timestamp=None):
    """{"Stripe-Signature": "t=<time>,v1=<signature>"} for this body.

    The same algorithm Stripe uses: HMAC-SHA256 of "<time>.<body>" with the
    webhook secret (settings.STRIPE_WEBHOOK_SECRET by default). A different
    secret or an old timestamp (> 5 minutes) gives an invalid signature.
    """
    secret = secret or settings.STRIPE_WEBHOOK_SECRET
    timestamp = int(time.time()) if timestamp is None else timestamp
    signed = f"{timestamp}.{payload}".encode()
    signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return {"Stripe-Signature": f"t={timestamp},v1={signature}"}


# ---------------------------------------------------------------------------
# Analytics without the network
# ---------------------------------------------------------------------------


class FakeAnalyticsResponse:
    """The part of requests.Response that AnalyticsClient reads."""

    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data
        self.text = text or (json.dumps(data) if data is not None else "")

    def json(self):
        if self._data is None:
            raise ValueError("Expecting value: line 1 column 1")  # what requests raises
        return self._data


@dataclass
class FakeAnalyticsCall:
    method: str
    path: str
    params: dict | None
    headers: dict | None
    json: dict | None


class FakeAnalyticsSession:
    """A requests.Session for AnalyticsClient: answers by the path, keeps the calls.

        session.answers["/api/reports/summary/"] = FakeAnalyticsResponse(200, {...})
            the same answer every time; a list = one answer per call, in order
        session.token_answers = [FakeAnalyticsResponse(401)]
            answers of POST /api/token/ (then "token-1", "token-2", ...)
        session.error = requests.ConnectionError("refused")
            every next call raises it (Analytics is down)
        session.calls          what the client sent (FakeAnalyticsCall)

    Analytics' reports of a normal answer: analytics_answers() below.
    """

    def __init__(self, answers=None):
        self.answers = dict(answers or {})
        self.token_answers = []
        self.error = None
        self.calls = []
        self._tokens = itertools.count(1)

    def request(self, method, url, timeout=None, params=None, json=None, headers=None):
        path = urlsplit(url).path
        self.calls.append(FakeAnalyticsCall(method, path, params, headers, json))
        if self.error is not None:
            raise self.error
        if path == "/api/token/":
            if self.token_answers:
                return self.token_answers.pop(0)
            return FakeAnalyticsResponse(200, {"access": f"token-{next(self._tokens)}"})
        answer = self.answers.get(path, FakeAnalyticsResponse(404, text="Not found"))
        if isinstance(answer, list):
            return answer.pop(0)
        return answer

    def report_calls(self):
        return [call for call in self.calls if call.path != "/api/token/"]


def _totals(orders, revenue, cancelled_share):
    return {
        "orders": orders,
        "paid_orders": orders - 1,
        "cancelled_orders": 1,
        "revenue_uah": revenue,
        "paid_revenue_uah": revenue,
        "items_sold": orders * 2,
        "average_order_uah": "700.00",
        "paid_share": "83.3",
        "cancelled_share": cancelled_share,
        "new_customers": 5,
        "returning_customers": 2,
    }


def analytics_answers(period=("2026-11-19", "2026-11-25"), books=()):
    """The answers of Analytics' four reports, in the shape of its serializers
    (reports/api.py of hillel_hw_34_django_analytics, the Swagger examples).

    books: (source_id, title) of the top books.
    """
    first, last = period
    period_json = {"from": first, "to": last, "days": 7}
    previous = {"from": "2026-11-12", "to": "2026-11-18", "days": 7}
    return {
        "/api/reports/summary/": FakeAnalyticsResponse(
            200,
            {
                "period": period_json,
                "previous_period": previous,
                "totals": _totals(12, "8400.00", "8.3"),
                "previous_totals": _totals(10, "7000.00", "10.0"),
                "changes": {
                    "orders": "20.0",
                    "paid_orders": "22.2",
                    "cancelled_orders": "0.0",
                    "revenue_uah": "20.0",
                    "paid_revenue_uah": "20.0",
                    "items_sold": "20.0",
                    "average_order_uah": "0.0",
                    "paid_share": "1.5",
                    "cancelled_share": "-17.0",
                    "new_customers": None,
                    "returning_customers": "0.0",
                },
            },
        ),
        "/api/reports/daily/": FakeAnalyticsResponse(
            200,
            {
                "period": period_json,
                "days": [
                    {"day": "2026-11-24", **_totals(5, "3500.00", "0.0")},
                    {"day": "2026-11-25", **_totals(7, "4900.00", "14.3")},
                ],
            },
        ),
        "/api/reports/top-books/": FakeAnalyticsResponse(
            200,
            {
                "period": period_json,
                "books": [
                    {
                        "source_id": source_id,
                        "title": title,
                        "author": "Taras Shevchenko",
                        "quantity": 5 - position,
                        "revenue_uah": f"{1750 - position * 100}.00",
                    }
                    for position, (source_id, title) in enumerate(books)
                ],
            },
        ),
        "/api/reports/formats/": FakeAnalyticsResponse(
            200,
            {
                "period": period_json,
                "formats": [
                    {
                        "format_type": "paper",
                        "quantity": 8,
                        "revenue_uah": "5600.00",
                        "revenue_share": "80.5",
                    },
                    {
                        "format_type": "audio",
                        "quantity": 2,
                        "revenue_uah": "1360.00",
                        "revenue_share": "19.5",
                    },
                ],
            },
        ),
    }
