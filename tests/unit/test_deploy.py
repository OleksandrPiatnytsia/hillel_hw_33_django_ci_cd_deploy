"""Running on a server: behind nginx with DEBUG=False (hw_31, stage 4),
gunicorn settings and covers served by Django on Railway (hw_33, stage 3)."""

import logging
import runpy
from pathlib import Path

import pytest
from django.test import RequestFactory
from django.views.defaults import server_error
from rest_framework.request import Request
from rest_framework.throttling import AnonRateThrottle


# Generated with AI
def test_anonymous_api_limit_ignores_a_made_up_x_forwarded_for():
    """The limit of anonymous clients is counted per REMOTE_ADDR.

    A client that sends its own X-Forwarded-For (a new fake address with
    every request) must still be the same client for the throttle.
    """
    http_request = RequestFactory().get(
        "/api/books/", REMOTE_ADDR="203.0.113.7", HTTP_X_FORWARDED_FOR="10.9.8.7"
    )

    ident = AnonRateThrottle().get_ident(Request(http_request))

    assert ident == "203.0.113.7"


# Generated with AI
def test_500_page_renders_without_the_request_context():
    """server_error renders templates/500.html with no context processors:
    the page must not depend on the user, the cart or the database."""
    response = server_error(RequestFactory().get("/"))

    assert response.status_code == 500
    html = response.content.decode()
    assert "<!DOCTYPE html>" in html
    assert 'href="/"' in html


# ---------------------------------------------------------------------------
# gunicorn.conf.py
# ---------------------------------------------------------------------------

GUNICORN_CONF = Path(__file__).resolve().parents[2] / "gunicorn.conf.py"


def test_gunicorn_listens_on_the_port_of_the_hosting(monkeypatch):
    """Railway sets PORT and sends its traffic there; WEB_CONCURRENCY = workers."""
    monkeypatch.setenv("PORT", "4321")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")

    conf = runpy.run_path(str(GUNICORN_CONF))

    assert conf["bind"] == "0.0.0.0:4321"
    assert conf["workers"] == 2
    assert conf["worker_class"] == "uvicorn_worker.UvicornWorker"


def test_gunicorn_defaults_for_docker_compose(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)

    conf = runpy.run_path(str(GUNICORN_CONF))

    assert conf["bind"] == "0.0.0.0:8000"  # nginx -> web:8000
    assert conf["workers"] == 3


# ---------------------------------------------------------------------------
# /media/: config.views.serve_media
# ---------------------------------------------------------------------------


@pytest.fixture
def cover(settings):
    """A file in MEDIA_ROOT (a temporary folder, see conftest.py)."""
    path = Path(settings.MEDIA_ROOT) / "covers" / "kobzar.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\x89PNG fake image")
    return "/media/covers/kobzar.png"


def test_media_is_not_served_without_the_flag(client, settings, cover):
    """Local Docker: nginx serves /media/, Django answers 404."""
    settings.DEBUG = False
    settings.SERVE_MEDIA = False

    assert client.get(cover).status_code == 404


@pytest.mark.parametrize("flag", ["DEBUG", "SERVE_MEDIA"])
def test_media_is_served_with_debug_or_the_flag(client, settings, cover, flag):
    """runserver (DEBUG) and Railway (DJANGO_SERVE_MEDIA=True)."""
    setattr(settings, flag, True)

    response = client.get(cover)

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert b"".join(response.streaming_content) == b"\x89PNG fake image"
    # A week in the browser, the same as nginx/default.conf
    assert "max-age=604800" in response["Cache-Control"]
    assert "public" in response["Cache-Control"]
    assert response["X-Content-Type-Options"] == "nosniff"


def test_media_refuses_paths_outside_media_root(client, settings, cover):
    settings.SERVE_MEDIA = True

    response = client.get("/media/../config/settings/base.py")

    assert response.status_code in (400, 404)


def test_media_answers_only_get_and_head(client, settings, cover):
    settings.SERVE_MEDIA = True

    assert client.head(cover).status_code == 200
    assert client.post(cover).status_code == 405


# ---------------------------------------------------------------------------
# config.middleware.RequestTimingMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url", ["/static/css/styles.css", "/media/covers/kobzar.png"])
def test_static_and_media_requests_are_not_logged(client, settings, cover, caplog, url):
    """On Railway every CSS / JS / cover goes through Django: no log line for
    each of them (the timing header is still added)."""
    settings.SERVE_MEDIA = True

    with caplog.at_level(logging.INFO, logger="config"):
        response = client.get(url)

    assert "X-Request-Duration" in response
    assert not [record for record in caplog.records if record.name == "config.middleware"]
