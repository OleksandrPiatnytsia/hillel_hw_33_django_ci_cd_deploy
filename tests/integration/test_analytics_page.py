"""The page /analytics/: the managers see the reports of Analytics.

The whole way inside the shop is real (the view, the period, the caches,
the client, the books of the catalog); only the network is the fake
Analytics of the `fake_analytics` fixture (tests/conftest.py).
"""

import logging
from datetime import timedelta
from decimal import Decimal

import pytest
import requests
from django.core.cache import cache
from django.urls import reverse

from analytics.client import DOWN_CACHE_KEY
from analytics.periods import last_days
from analytics.reports import cache_key

from ..factories import BookFactory, UserFactory
from ..fakes import FakeAnalyticsResponse, analytics_answers

pytestmark = pytest.mark.django_db

URL = reverse("analytics:sales")


@pytest.fixture(autouse=True)
def _english(settings):
    # The texts are checked in English; the site's default language is uk
    # (one test below checks the Ukrainian page with the language cookie)
    settings.LANGUAGE_CODE = "en"


# Generated with AI
def test_anonymous_goes_to_the_login_page(client, fake_analytics):
    response = client.get(URL)

    assert response.status_code == 302
    assert response.url.startswith(reverse("users:login"))
    assert fake_analytics.calls == []


# Generated with AI
@pytest.mark.parametrize("groups", [["Customers"], ["Editors"], ["Services"]])
def test_without_the_right_the_page_is_forbidden(client, fake_analytics, groups):
    client.force_login(UserFactory(groups=groups))

    assert client.get(URL).status_code == 403
    assert fake_analytics.calls == []


# Generated with AI
def test_managers_see_the_tiles_with_the_changes(manager_client, fake_analytics):
    response = manager_client.get(URL)

    assert response.status_code == 200
    tiles = {str(tile.label): tile for tile in response.context["tiles"]}
    assert tiles["Revenue"].value == Decimal("8400.00")
    assert (tiles["Revenue"].change, tiles["Revenue"].good) == (Decimal("20.0"), True)
    # Fewer cancellations is good news: a green arrow down
    assert (tiles["Cancelled"].change, tiles["Cancelled"].good) == (Decimal("-17.0"), True)
    # No customers in the previous period: no percent at all
    assert (tiles["New customers"].change, tiles["New customers"].good) == (None, None)
    content = response.content.decode()
    assert "▲ +20.0 %" in content
    assert "▼ -17.0 %" in content
    assert "Analytics is temporarily unavailable" not in content


# Generated with AI
def test_one_login_and_four_reports_with_the_real_dates(manager_client, fake_analytics):
    manager_client.get(URL)

    period = last_days(30)
    assert [call.path for call in fake_analytics.calls] == [
        "/api/token/",
        "/api/reports/summary/",
        "/api/reports/daily/",
        "/api/reports/top-books/",
        "/api/reports/formats/",
    ]
    calls = fake_analytics.report_calls()
    assert all(call.params["from"] == period.first.isoformat() for call in calls)
    assert all(call.params["to"] == period.last.isoformat() for call in calls)
    assert calls[2].params["limit"] == 10


# Generated with AI
def test_the_next_view_comes_from_the_cache(manager_client, fake_analytics):
    manager_client.get(URL)
    calls = len(fake_analytics.calls)

    response = manager_client.get(URL)

    assert len(fake_analytics.calls) == calls
    assert response.context["tiles"]


# Generated with AI
def test_a_preset_and_chosen_dates(manager_client, fake_analytics):
    manager_client.get(URL, {"period": "7"})
    manager_client.get(URL, {"from": "2026-11-01", "to": "2026-11-30"})

    summaries = [call for call in fake_analytics.calls if call.path == "/api/reports/summary/"]
    week = last_days(7)
    assert summaries[0].params == {"from": week.first.isoformat(), "to": week.last.isoformat()}
    assert summaries[1].params == {"from": "2026-11-01", "to": "2026-11-30"}


# Generated with AI
def test_a_wrong_period_shows_the_reason_and_the_default_period(manager_client, fake_analytics):
    response = manager_client.get(URL, {"from": "2026-11-30", "to": "2026-11-01"})

    assert response.status_code == 200
    assert "later than its end" in response.context["period_error"]
    assert response.context["period"].preset == 30


# Generated with AI
def test_the_chart_data_and_the_table_of_the_days(manager_client, fake_analytics):
    response = manager_client.get(URL)

    chart = response.context["chart"]
    assert chart["labels"] == ["24.11", "25.11"]
    assert chart["revenue"] == ["3500.00", "4900.00"]  # strings: no float rounding
    assert chart["orders"] == [5, 7]
    content = response.content.decode()
    assert 'id="revenue-chart-data"' in content
    assert "chart.umd.min.js" in content
    # The table is the report without JavaScript
    assert "25.11.2026" in content


# Generated with AI
def test_top_books_link_to_the_catalog_with_the_stock_now(manager_client, fake_analytics):
    kobzar = BookFactory(title="Kobzar", stock=2)
    zakhar = BookFactory(title="Zakhar Berkut", stock=40)
    fake_analytics.answers.update(
        analytics_answers(
            books=[(kobzar.pk, "Kobzar"), (zakhar.pk, "Zakhar Berkut"), (999999, "Gone")]
        )
    )

    response = manager_client.get(URL)

    rows = response.context["top_books"]
    assert [row["book"] for row in rows] == [kobzar, zakhar, None]
    assert [row["book"].stock for row in rows[:2]] == [2, 40]
    content = response.content.decode()
    assert f'href="{kobzar.get_absolute_url()}"' in content
    # Low stock is marked: time to order more of a best seller
    assert '<span class="badge text-bg-warning">2</span>' in content
    assert "Gone" in content


# Generated with AI
def test_no_sales_is_an_empty_table_not_an_error(manager_client, fake_analytics):
    response = manager_client.get(URL)

    assert response.context["top_books"] == []
    assert "No sales in this period." in response.content.decode()


# Generated with AI
def test_formats_have_the_labels_of_the_shop(manager_client, fake_analytics):
    response = manager_client.get(URL)

    formats = response.context["formats"]
    assert [(str(row["label"]), row["share"]) for row in formats] == [
        ("Paper", Decimal("80.5")),
        ("Audiobook", Decimal("19.5")),
    ]
    # The width of the bar is a number with a dot in any language
    assert "width: 80.5%" in response.content.decode()


# Generated with AI
def test_analytics_down_the_page_still_works(manager_client, fake_analytics, caplog):
    fake_analytics.error = requests.ConnectionError("Connection refused")

    with caplog.at_level(logging.WARNING):
        response = manager_client.get(URL)

    assert response.status_code == 200
    assert response.context["unavailable"] is True
    assert response.context["tiles"] == []
    assert response.context["top_books"] is None
    assert "Analytics is temporarily unavailable" in response.content.decode()
    assert "Analytics is not reachable" in caplog.text
    assert "shown without fresh data: unavailable" in caplog.text
    # Only the first request was tried: the circuit breaker stopped the others
    assert len(fake_analytics.calls) == 1
    assert cache.get(DOWN_CACHE_KEY) is True


# Generated with AI
def test_analytics_down_shows_the_last_good_numbers_with_their_time(manager_client, fake_analytics):
    manager_client.get(URL)
    period = last_days(30)
    # The fresh copies expired, the last good ones are still there
    for name, params in [
        ("summary", {}),
        ("daily", {}),
        ("top-books", {"limit": 10}),
        ("formats", {}),
    ]:
        cache.delete(cache_key(name, {**period.query, **params}))
    fake_analytics.error = requests.ConnectionError("Connection refused")

    response = manager_client.get(URL)

    assert response.context["stale_since"] is not None
    assert response.context["tiles"][0].value == Decimal("8400.00")
    content = response.content.decode()
    assert "Analytics is temporarily unavailable" in content
    assert "The numbers below are as of" in content


# Generated with AI
def test_a_refused_account_is_a_different_message(manager_client, fake_analytics, caplog):
    fake_analytics.token_answers = [FakeAnalyticsResponse(401, {"detail": "No active account"})] * 4

    with caplog.at_level(logging.ERROR, "analytics.client"):
        response = manager_client.get(URL)

    assert response.context["refused"] is True
    assert "The administrator has been notified" in response.content.decode()
    assert "refused the login" in caplog.text


# Generated with AI
def test_not_configured_says_so_and_calls_nothing(manager_client, fake_analytics, settings):
    settings.ANALYTICS_API_URL = ""

    response = manager_client.get(URL)

    assert response.status_code == 200
    assert response.context["not_configured"] is True
    assert "not connected to this shop yet" in response.content.decode()
    assert fake_analytics.calls == []


# Generated with AI
def test_the_link_to_analytics_only_when_it_has_an_address(
    manager_client, fake_analytics, settings
):
    assert 'href="http://analytics.example/"' in manager_client.get(URL).content.decode()

    settings.ANALYTICS_PUBLIC_URL = ""
    assert "Open in Analytics" not in manager_client.get(URL).content.decode()


# Generated with AI
def test_the_navbar_and_the_profile_link_only_for_managers(client, manager, customer):
    client.force_login(customer)
    assert URL not in client.get(reverse("users:profile")).content.decode()

    client.force_login(manager)
    content = client.get(reverse("users:profile")).content.decode()
    # The navbar menu and the profile section
    assert content.count(f'href="{URL}"') == 2


# Generated with AI
def test_the_page_in_ukrainian(manager_client, fake_analytics, settings):
    manager_client.cookies[settings.LANGUAGE_COOKIE_NAME] = "uk"

    content = manager_client.get(URL).content.decode()

    assert "Аналітика продажів" in content
    assert "Виторг" in content
    assert "Паперова" in content


# Generated with AI
def test_the_stale_time_is_the_oldest_shown_answer(manager_client, fake_analytics):
    """Two copies of different age: the message names the older one."""
    manager_client.get(URL)
    period = last_days(30)
    cache.delete(cache_key("summary", period.query))
    cache.delete(cache_key("daily", period.query))
    older = cache.get(cache_key("summary", period.query) + ":last-good")
    older["fetched_at"] -= timedelta(hours=2)
    cache.set(cache_key("summary", period.query) + ":last-good", older)
    fake_analytics.error = requests.ConnectionError("refused")

    response = manager_client.get(URL)

    assert response.context["stale_since"] == older["fetched_at"]
