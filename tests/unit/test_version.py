"""The version of the site in the footer (config/version.py, config/context_processors.py)."""

import re

import pytest
from django.urls import reverse

from config import version
from config.context_processors import version as version_context

SHA = "335de9f0123456789abcdef0123456789abcdef0"


# Generated with AI
def test_the_version_is_major_minor_patch():
    assert re.fullmatch(r"\d+\.\d+\.\d+", version.__version__)


# Generated with AI
def test_the_commit_comes_from_railway_first(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", SHA)
    monkeypatch.setenv("APP_COMMIT", "other")

    assert version.deployed_commit() == SHA


# Generated with AI
def test_the_commit_falls_back_to_app_commit_and_then_to_nothing(monkeypatch):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.setenv("APP_COMMIT", SHA)
    assert version.deployed_commit() == SHA

    monkeypatch.delenv("APP_COMMIT")
    assert version.deployed_commit() == ""


# Generated with AI
def test_context_has_the_version_and_a_link_to_the_commit(settings, rf):
    settings.APP_COMMIT = SHA

    context = version_context(rf.get("/"))

    assert context["app_version"] == settings.APP_VERSION
    assert context["app_commit"] == SHA
    assert context["app_commit_url"] == f"{settings.APP_REPOSITORY_URL}/commit/{SHA}"


# Generated with AI
def test_context_without_a_commit_has_no_link(settings, rf):
    settings.APP_COMMIT = ""

    assert version_context(rf.get("/"))["app_commit_url"] == ""


# Generated with AI
@pytest.mark.django_db
def test_footer_shows_the_version_and_the_short_commit(client, settings):
    settings.APP_VERSION = "1.2.3"
    settings.APP_COMMIT = SHA

    html = client.get(reverse("books:list")).content.decode()

    assert "v1.2.3" in html
    assert f'href="{settings.APP_REPOSITORY_URL}/commit/{SHA}"' in html
    assert ">335de9f<" in html


# Generated with AI
@pytest.mark.django_db
def test_footer_without_a_commit_shows_only_the_version(client, settings):
    settings.APP_VERSION = "1.2.3"
    settings.APP_COMMIT = ""

    html = client.get(reverse("books:list")).content.decode()

    assert "v1.2.3" in html
    assert "/commit/" not in html


# Generated with AI
@pytest.mark.django_db
def test_footer_homework_text_links_to_the_course(client):
    html = client.get(reverse("books:list")).content.decode()
    footer = html[html.index("<footer") :]

    link = re.search(
        r'<a [^>]*href="https://ithillel.ua/courses/python-pro"[^>]*>(.*?)</a>', footer
    )
    assert link.group(1) == "домашнє завдання Hillel з Django"
    assert 'target="_blank" rel="noopener"' in link.group(0)
    assert "Книгарня ·" in footer
