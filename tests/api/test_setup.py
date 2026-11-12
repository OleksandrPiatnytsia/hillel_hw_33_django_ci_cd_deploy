"""The base of the API: JWT tokens, the request limit of the login,
the documentation, CORS and the root page /api/.

The URLs are written as text ("/api/token/"), not reverse("api:..."): the
tests also check that the API lives at the addresses written in README
and the documentation.
"""

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# JWT: obtain, refresh, verify
# ---------------------------------------------------------------------------


def test_token_obtain_returns_access_and_refresh_for_valid_password(customer, get_tokens):
    tokens = get_tokens(customer)

    assert set(tokens) == {"access", "refresh"}
    # The access token is issued for this user (claim "user_id")
    assert str(AccessToken(tokens["access"])["user_id"]) == str(customer.pk)


def test_token_obtain_with_wrong_password_is_401(api_client, customer):
    response = api_client.post(
        "/api/token/",
        {"username": customer.username, "password": "wrong-password"},
        format="json",
    )

    assert response.status_code == 401
    assert "access" not in response.json()


def test_token_obtain_for_inactive_user_is_401(api_client):
    # A blocked account (is_active=False in the admin) gets no tokens
    blocked = UserFactory(username="blocked", is_active=False)

    response = api_client.post(
        "/api/token/",
        {"username": blocked.username, "password": "Test-pass-123"},
        format="json",
    )

    assert response.status_code == 401


def test_token_refresh_gives_a_new_access_token(api_client, customer, get_tokens):
    tokens = get_tokens(customer)

    response = api_client.post("/api/token/refresh/", {"refresh": tokens["refresh"]}, format="json")

    assert response.status_code == 200
    new_access = response.json()["access"]
    assert str(AccessToken(new_access)["user_id"]) == str(customer.pk)


def test_token_refresh_does_not_accept_an_access_token(api_client, customer, get_tokens):
    # The token type is inside the token: an access token can't be used to
    # get new tokens, even before it expires
    tokens = get_tokens(customer)

    response = api_client.post("/api/token/refresh/", {"refresh": tokens["access"]}, format="json")

    assert response.status_code == 401


def test_token_verify_valid_and_broken_token(api_client, customer, get_tokens):
    tokens = get_tokens(customer)

    valid = api_client.post("/api/token/verify/", {"token": tokens["access"]}, format="json")
    # The last character changed: the signature doesn't match any more
    broken_token = tokens["access"][:-1] + ("A" if tokens["access"][-1] != "A" else "B")
    broken = api_client.post("/api/token/verify/", {"token": broken_token}, format="json")

    assert valid.status_code == 200
    assert broken.status_code == 401


def test_broken_bearer_token_is_refused_not_ignored(api_client):
    # Even on a public page: a client that sends a bad token must learn
    # about it (401), not quietly become anonymous
    api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

    response = api_client.get("/api/")

    assert response.status_code == 401


def test_token_obtain_is_limited_to_10_requests_per_minute(api_client, customer):
    # DEFAULT_THROTTLE_RATES["token"] = "10/minute", per IP address.
    # The counters are in the cache, cleared before every test (conftest.py).
    data = {"username": customer.username, "password": "wrong-password"}

    statuses = [api_client.post("/api/token/", data, format="json").status_code for _ in range(10)]
    eleventh = api_client.post("/api/token/", data, format="json")

    assert statuses == [401] * 10
    assert eleventh.status_code == 429
    # How many seconds to wait, for the client
    assert int(eleventh["Retry-After"]) > 0


# ---------------------------------------------------------------------------
# The root page and the documentation
# ---------------------------------------------------------------------------


def test_api_root_is_open_without_login(api_client):
    response = api_client.get("/api/")

    assert response.status_code == 200


def test_openapi_schema_describes_the_token_endpoints(api_client):
    response = api_client.get("/api/schema/")

    assert response.status_code == 200
    schema = response.content.decode()
    assert "openapi: 3" in schema
    assert "Bookstore API" in schema
    assert "/api/token/:" in schema
    assert "/api/token/refresh/:" in schema


@pytest.mark.parametrize("url", ["/api/docs/", "/api/redoc/"])
def test_documentation_pages_open(api_client, url):
    response = api_client.get(url)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    # The page loads the schema from /api/schema/
    assert "/api/schema/" in response.content.decode()


# ---------------------------------------------------------------------------
# CORS (config/settings/test.py: CORS_ALLOWED_ORIGINS = ["http://localhost:3000"])
# ---------------------------------------------------------------------------


def test_cors_header_for_an_allowed_origin_on_the_api(api_client):
    response = api_client.get("/api/", HTTP_ORIGIN="http://localhost:3000")

    assert response["Access-Control-Allow-Origin"] == "http://localhost:3000"


def test_no_cors_header_for_an_unknown_origin(api_client):
    response = api_client.get("/api/", HTTP_ORIGIN="https://evil.example.com")

    assert "Access-Control-Allow-Origin" not in response


def test_no_cors_header_on_the_site_pages(api_client):
    # CORS_URLS_REGEX: only /api/. The catalog page of the site stays closed
    # even for an allowed origin
    response = api_client.get("/", HTTP_ORIGIN="http://localhost:3000")

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response


def test_cors_preflight_allows_the_authorization_header(api_client):
    # Before a POST with "Authorization: Bearer ..." from another domain the
    # browser asks first: OPTIONS + Access-Control-Request-* headers
    response = api_client.options(
        "/api/token/",
        HTTP_ORIGIN="http://localhost:3000",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization, content-type",
    )

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert "authorization" in response["Access-Control-Allow-Headers"]


def test_cors_allows_the_idempotency_key_header(api_client):
    # Without "idempotency-key" in CORS_ALLOW_HEADERS a browser would not
    # send POST /api/orders/ with this header at all
    response = api_client.options(
        "/api/orders/",
        HTTP_ORIGIN="http://localhost:3000",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization, content-type, idempotency-key",
    )

    assert response.status_code == 200
    assert "idempotency-key" in response["Access-Control-Allow-Headers"]
