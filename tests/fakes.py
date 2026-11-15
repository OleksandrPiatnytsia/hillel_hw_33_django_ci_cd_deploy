"""Fakes of external services: Stripe without the network.

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
from types import SimpleNamespace

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
