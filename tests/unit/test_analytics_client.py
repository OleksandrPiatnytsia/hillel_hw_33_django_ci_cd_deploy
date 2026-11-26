"""The client of Analytics' REST API, its periods and its caches (app analytics).

No network: the `fake_analytics` fixture (tests/conftest.py) gives every
AnalyticsClient a FakeAnalyticsSession (tests/fakes.py) that answers like
Analytics' report API.
"""

import logging
from datetime import date, datetime, timezone as dt_timezone

import pytest
import requests
from django.core.cache import cache
from django.utils import timezone, translation

from analytics.client import (
    DOWN_CACHE_KEY,
    TOKEN_CACHE_KEY,
    AnalyticsClient,
    AnalyticsNotConfigured,
    AnalyticsRefused,
    AnalyticsUnavailable,
)
from analytics.periods import MAX_DAYS, Period, PeriodError, parse_period
from analytics.reports import cache_key, fetch_report

from ..fakes import FakeAnalyticsResponse

SUMMARY = "/api/reports/summary/"
QUERY = {"from": "2026-11-19", "to": "2026-11-25"}


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------


# Generated with AI
def test_client_logs_in_once_and_sends_the_token(fake_analytics):
    client = AnalyticsClient()

    answer = client.get(SUMMARY, QUERY)
    client.get(SUMMARY, QUERY)

    assert answer["totals"]["revenue_uah"] == "8400.00"
    token_call, *report_calls = fake_analytics.calls
    assert (token_call.method, token_call.path) == ("POST", "/api/token/")
    assert token_call.json == {"username": "bookstore-service", "password": "test-password"}
    assert len(report_calls) == 2  # the second GET without a new login
    assert report_calls[0].headers == {"Authorization": "Bearer token-1"}
    assert report_calls[0].params == QUERY


# Generated with AI
def test_the_token_is_shared_through_the_cache(fake_analytics):
    AnalyticsClient().get(SUMMARY)
    # Another worker / another page view: a new client, the same token
    AnalyticsClient().get(SUMMARY)

    assert [call.path for call in fake_analytics.calls].count("/api/token/") == 1
    assert cache.get(TOKEN_CACHE_KEY) == "token-1"


# Generated with AI
def test_an_expired_token_is_replaced_once(fake_analytics):
    fake_analytics.answers[SUMMARY] = [
        FakeAnalyticsResponse(401, {"detail": "Token is expired"}),
        FakeAnalyticsResponse(200, {"totals": {}}),
    ]

    assert AnalyticsClient().get(SUMMARY) == {"totals": {}}
    report_calls = fake_analytics.report_calls()
    assert [call.headers["Authorization"] for call in report_calls] == [
        "Bearer token-1",
        "Bearer token-2",
    ]


# Generated with AI
def test_a_second_401_means_the_account_is_refused(fake_analytics, caplog):
    fake_analytics.answers[SUMMARY] = FakeAnalyticsResponse(401, {"detail": "no"})

    with pytest.raises(AnalyticsRefused), caplog.at_level(logging.ERROR, "analytics.client"):
        AnalyticsClient().get(SUMMARY)

    assert len(fake_analytics.report_calls()) == 2
    assert "group Services" in caplog.text
    # A refusal is a mistake of the settings, not "down": no circuit breaker
    assert cache.get(DOWN_CACHE_KEY) is None


# Generated with AI
def test_no_permission_in_analytics_is_refused(fake_analytics):
    fake_analytics.answers[SUMMARY] = FakeAnalyticsResponse(403, {"detail": "no"})

    with pytest.raises(AnalyticsRefused):
        AnalyticsClient().get(SUMMARY)


# Generated with AI
def test_a_wrong_login_is_refused_without_the_password_in_the_log(fake_analytics, caplog):
    fake_analytics.token_answers = [FakeAnalyticsResponse(401, {"detail": "No active account"})]

    with pytest.raises(AnalyticsRefused), caplog.at_level(logging.DEBUG):
        AnalyticsClient().get(SUMMARY)

    assert "bookstore-service" in caplog.text
    assert "test-password" not in caplog.text
    assert fake_analytics.report_calls() == []


# Generated with AI
def test_a_token_answer_without_a_token_is_unavailable(fake_analytics):
    fake_analytics.token_answers = [FakeAnalyticsResponse(200, {"refresh": "x"})]

    with pytest.raises(AnalyticsUnavailable):
        AnalyticsClient().get(SUMMARY)


# Generated with AI
def test_a_bad_request_is_refused_and_logged_with_the_reason(fake_analytics, caplog):
    fake_analytics.answers[SUMMARY] = FakeAnalyticsResponse(400, {"to": ["Bad date"]})

    with pytest.raises(AnalyticsRefused), caplog.at_level(logging.ERROR, "analytics.client"):
        AnalyticsClient().get(SUMMARY)

    assert "Bad date" in caplog.text


# Generated with AI
@pytest.mark.parametrize(
    "answer",
    [
        FakeAnalyticsResponse(500, text="Server Error"),
        FakeAnalyticsResponse(503, text="Bad Gateway"),
        FakeAnalyticsResponse(429, {"detail": "throttled"}),
        FakeAnalyticsResponse(200, None, text="<html>nginx</html>"),  # not JSON
        FakeAnalyticsResponse(200, ["a", "list"]),  # JSON, not an object
    ],
)
def test_server_errors_mean_unavailable(fake_analytics, answer):
    fake_analytics.answers[SUMMARY] = answer

    with pytest.raises(AnalyticsUnavailable):
        AnalyticsClient().get(SUMMARY)


# Generated with AI
def test_no_connection_is_unavailable_and_logged(fake_analytics, caplog):
    fake_analytics.error = requests.ConnectTimeout("timed out")

    with pytest.raises(AnalyticsUnavailable), caplog.at_level(logging.WARNING, "analytics.client"):
        AnalyticsClient().get(SUMMARY)

    assert "not reachable" in caplog.text
    assert "http://analytics.test/api/token/" in caplog.text


# Generated with AI
def test_after_a_failure_analytics_is_not_called_for_a_while(fake_analytics, settings):
    fake_analytics.error = requests.ConnectionError("refused")
    with pytest.raises(AnalyticsUnavailable):
        AnalyticsClient().get(SUMMARY)
    calls = len(fake_analytics.calls)
    fake_analytics.error = None

    # The circuit breaker: the next pages don't wait for the timeouts again
    with pytest.raises(AnalyticsUnavailable):
        AnalyticsClient().get(SUMMARY)
    assert len(fake_analytics.calls) == calls

    # After ANALYTICS_DOWN_TIMEOUT the key expires: Analytics is asked again
    cache.delete(DOWN_CACHE_KEY)
    assert AnalyticsClient().get(SUMMARY)["totals"]


# Generated with AI
@pytest.mark.parametrize("setting", ["ANALYTICS_API_URL", "ANALYTICS_API_PASSWORD"])
def test_not_configured_calls_nothing(fake_analytics, settings, setting):
    setattr(settings, setting, "")

    with pytest.raises(AnalyticsNotConfigured):
        AnalyticsClient().get(SUMMARY)
    assert fake_analytics.calls == []


# Generated with AI
def test_the_real_session_retries_a_gateway_error_once():
    session = AnalyticsClient.make_session()

    retry = session.get_adapter("http://analytics.test/").max_retries
    assert retry.total == 1
    assert 502 in retry.status_forcelist
    assert {"GET", "POST"} <= retry.allowed_methods


# ---------------------------------------------------------------------------
# The period
# ---------------------------------------------------------------------------


@pytest.fixture
def kyiv_evening(monkeypatch):
    # 22:30 UTC on the 24th is 00:30 on the 25th in Kyiv: "today" is the 25th,
    # as in Analytics, whose report days are days in Kyiv
    moment = datetime(2026, 11, 24, 22, 30, tzinfo=dt_timezone.utc)
    monkeypatch.setattr(timezone, "now", lambda: moment)


# Generated with AI
@pytest.mark.parametrize(
    "query, first, preset",
    [
        ({}, date(2026, 10, 27), 30),
        ({"period": "7"}, date(2026, 11, 19), 7),
        ({"period": "90"}, date(2026, 8, 28), 90),
    ],
)
def test_presets_end_today_in_kyiv(kyiv_evening, query, first, preset):
    period = parse_period(query)

    assert (period.first, period.last, period.preset) == (first, date(2026, 11, 25), preset)
    assert period.days == preset


# Generated with AI
def test_chosen_dates():
    period = parse_period({"from": "2026-11-01", "to": "2026-11-30"})

    assert period == Period(date(2026, 11, 1), date(2026, 11, 30))
    assert period.query == {"from": "2026-11-01", "to": "2026-11-30"}
    assert period.days == 30


# Generated with AI
@pytest.mark.parametrize(
    "query, reason",
    [
        ({"from": "2026-11-01"}, "both dates"),
        ({"from": "2026-11-01", "to": "2026-13-01"}, "not a valid date"),
        ({"from": "2026-11-30", "to": "2026-11-01"}, "later than its end"),
        ({"from": "2025-01-01", "to": "2026-11-30"}, f"longer than {MAX_DAYS} days"),
        ({"period": "14"}, "Unknown period"),
        ({"period": "seven"}, "Unknown period"),
    ],
)
def test_wrong_periods(query, reason):
    with translation.override("en"), pytest.raises(PeriodError, match=reason):
        parse_period(query)


# ---------------------------------------------------------------------------
# The caches of the answers
# ---------------------------------------------------------------------------

PERIOD = Period(date(2026, 11, 19), date(2026, 11, 25))


# Generated with AI
def test_cache_keys_hold_the_real_dates_in_a_fixed_order():
    assert cache_key("top-books", {"to": "2026-11-25", "limit": 10, "from": "2026-11-19"}) == (
        "analytics:report:top-books:from=2026-11-19&limit=10&to=2026-11-25"
    )


# Generated with AI
def test_a_fresh_answer_is_taken_from_the_cache(fake_analytics):
    client = AnalyticsClient()
    first = fetch_report("summary", PERIOD, client)
    second = fetch_report("summary", PERIOD, client)

    assert first.data == second.data
    assert (first.stale, first.problem) == (False, "")
    assert len(fake_analytics.report_calls()) == 1


# Generated with AI
def test_extra_parameters_go_to_analytics(fake_analytics):
    fetch_report("top-books", PERIOD, AnalyticsClient(), limit=10)

    assert fake_analytics.report_calls()[0].params == {**PERIOD.query, "limit": 10}


# Generated with AI
def test_without_analytics_the_last_good_answer_is_shown(fake_analytics):
    good = fetch_report("summary", PERIOD, AnalyticsClient())
    cache.delete(cache_key("summary", PERIOD.query))  # the fresh copy expired
    fake_analytics.error = requests.ConnectionError("refused")

    result = fetch_report("summary", PERIOD, AnalyticsClient())

    assert result.data == good.data
    assert (result.stale, result.problem) == (True, "unavailable")
    assert result.fetched_at == good.fetched_at


# Generated with AI
@pytest.mark.parametrize(
    "setup, problem",
    [
        (lambda session, settings: setattr(settings, "ANALYTICS_API_URL", ""), "not_configured"),
        (
            lambda session, settings: setattr(session, "error", requests.ConnectionError("x")),
            "unavailable",
        ),
        (
            lambda session, settings: session.token_answers.append(FakeAnalyticsResponse(401)),
            "refused",
        ),
    ],
)
def test_problems_without_a_good_answer(fake_analytics, settings, setup, problem):
    setup(fake_analytics, settings)

    result = fetch_report("summary", PERIOD, AnalyticsClient())

    assert (result.data, result.stale, result.problem) == (None, False, problem)
