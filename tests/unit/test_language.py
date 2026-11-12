"""Unit tests: which language a request gets, and the switcher view.

LocaleMiddleware puts the chosen language into the "Content-Language"
header of every response: the tests read it there.
"""

import pytest
from django.conf import settings
from django.urls import reverse

pytestmark = pytest.mark.django_db

COOKIE = settings.LANGUAGE_COOKIE_NAME  # "django_language"


def language_of(response):
    return response["Content-Language"]


def test_default_language_is_ukrainian(client):
    response = client.get(reverse("books:list"))

    assert language_of(response) == "uk"
    assert '<html lang="uk">' in response.content.decode()


@pytest.mark.parametrize(
    ("accept_language", "expected"),
    [("en-US,en;q=0.9", "en"), ("uk,en;q=0.5", "uk"), ("de-DE,de;q=0.9", "uk")],
)
def test_first_visit_uses_browser_language_if_supported(client, accept_language, expected):
    response = client.get(reverse("books:list"), headers={"Accept-Language": accept_language})

    assert language_of(response) == expected


def test_cookie_wins_over_browser_language(client):
    client.cookies[COOKIE] = "en"

    response = client.get(reverse("books:list"), headers={"Accept-Language": "uk"})

    assert language_of(response) == "en"


def test_navbar_has_switcher_with_both_languages(client):
    html = client.get(reverse("books:list")).content.decode()

    assert f'action="{reverse("set_language")}"' in html
    assert 'name="language" value="uk"' in html
    assert 'name="language" value="en"' in html


def test_set_language_accepts_only_post(client):
    assert client.get(reverse("set_language"), {"language": "en"}).status_code == 405


def test_set_language_sets_cookie_and_returns_to_next(client):
    response = client.post(reverse("set_language"), {"language": "en", "next": "/authors/?page=2"})

    assert response.status_code == 302
    assert response.url == "/authors/?page=2"
    assert response.cookies[COOKIE].value == "en"
    assert response.cookies[COOKIE]["max-age"] == settings.LANGUAGE_COOKIE_AGE


def test_set_language_ignores_unsupported_language(customer, customer_client):
    response = customer_client.post(reverse("set_language"), {"language": "de", "next": "/"})

    assert COOKIE not in response.cookies
    customer.refresh_from_db()
    assert customer.language == "uk"


def test_set_language_does_not_redirect_to_another_site(client):
    response = client.post(
        reverse("set_language"), {"language": "en", "next": "https://evil.example/"}
    )

    assert response.url == "/"
