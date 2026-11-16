"""Currencies and exchange rates: the tables, conversion, the NBU update.

The NBU is never called: requests.get in currencies.nbu is replaced by
a fake that returns a prepared answer (the `nbu` fixture).
"""

import json
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest
import requests
from django.core.management import CommandError, call_command
from django.db import IntegrityError
from django.urls import reverse

from config.celery import app as celery_app
from currencies import nbu
from currencies.models import Currency, ExchangeRate
from currencies.services import (
    RateUnavailable,
    available_currencies,
    convert,
    cross_rate,
    current_rates,
    today,
    update_rates,
)
from currencies.tasks import update_exchange_rates

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 16)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    """services.today() is 16.11.2026 in every test of this file."""
    monkeypatch.setattr("currencies.services.today", lambda: TODAY)


def add_rate(code, rate, day=TODAY, source=ExchangeRate.Source.NBU):
    return ExchangeRate.objects.create(
        currency_id=code, date=day, rate=Decimal(rate), source=source
    )


@pytest.fixture
def rates():
    add_rate("USD", "45.4274")
    add_rate("EUR", "50.3379")


class FakeResponse:
    def __init__(self, body, status=200):
        self.text = body if isinstance(body, str) else json.dumps(body)
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error")

    def json(self, **kwargs):
        return json.loads(self.text, **kwargs)


@pytest.fixture
def nbu_answer(monkeypatch):
    """Set .body (and .status) of the next NBU answer; .requests lists the calls."""

    class Answer:
        # The real format, as text: the numbers are JSON numbers, not strings
        body = (
            '[{"r030":840,"txt":"Долар США","rate":45.4274,"cc":"USD",'
            '"exchangedate":"17.11.2026","special":"N"},'
            '{"r030":978,"txt":"Євро","rate":50.3379,"cc":"EUR",'
            '"exchangedate":"17.11.2026","special":null},'
            '{"r030":985,"txt":"Злотий","rate":11.2,"cc":"PLN",'
            '"exchangedate":"17.11.2026","special":null}]'
        )
        status = 200
        requests = []
        # True: a request with &date= gets the rates of that day (like the
        # real NBU); False: every answer is the body above (17.11)
        follow_date = False

    def fake_get(url, params=None, timeout=None):
        Answer.requests.append({"url": url, "params": params, "timeout": timeout})
        body = Answer.body
        if Answer.follow_date and "date" in params:
            day = datetime.strptime(params["date"], "%Y%m%d")
            body = body.replace("17.11.2026", f"{day:%d.%m.%Y}")
        return FakeResponse(body, Answer.status)

    monkeypatch.setattr(nbu.requests, "get", fake_get)
    return Answer


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


# Generated with AI
def test_the_data_migration_creates_the_three_currencies():
    assert list(Currency.objects.values_list("code", "symbol")) == [
        ("EUR", "€"),
        ("UAH", "₴"),
        ("USD", "$"),
    ]


# Generated with AI
def test_one_rate_per_currency_per_day():
    add_rate("USD", "45")
    with pytest.raises(IntegrityError):
        add_rate("USD", "46")


# Generated with AI
def test_the_base_currency_has_no_rate_rows():
    with pytest.raises(IntegrityError):
        add_rate("UAH", "1")


# Generated with AI
def test_a_rate_must_be_positive():
    with pytest.raises(IntegrityError):
        add_rate("USD", "0")


# ---------------------------------------------------------------------------
# Current rates and conversion
# ---------------------------------------------------------------------------


# Generated with AI
def test_today_is_the_date_in_kyiv(monkeypatch):
    monkeypatch.undo()  # the real today(), not the fixed one
    # 23:30 UTC on the 16th is 01:30 on the 17th in Kyiv (UTC+2 in winter)
    late_evening = datetime(2026, 11, 16, 23, 30, tzinfo=dt_timezone.utc)
    monkeypatch.setattr("django.utils.timezone.now", lambda: late_evening)

    assert today() == date(2026, 11, 17)


# Generated with AI
def test_current_rate_is_the_newest_up_to_today():
    add_rate("USD", "44.00", TODAY - timedelta(days=3))
    add_rate("USD", "45.00", TODAY - timedelta(days=1))
    # Published in the afternoon for tomorrow: not in force yet
    add_rate("USD", "46.00", TODAY + timedelta(days=1))

    rates = current_rates()

    assert rates["USD"].value == Decimal("45.00")
    assert rates["USD"].date == TODAY - timedelta(days=1)
    assert rates["UAH"].value == 1
    assert "EUR" not in rates  # no rate at all


# Generated with AI
def test_a_turned_off_currency_keeps_its_last_rate():
    add_rate("EUR", "50")
    Currency.objects.filter(code="EUR").update(is_active=False)

    # Books with a price in EUR can still be converted...
    assert current_rates()["EUR"].value == 50
    # ...but EUR is not offered any more
    assert [currency.code for currency in available_currencies()] == ["UAH"]


# Generated with AI
def test_current_rates_are_cached(rates, django_assert_num_queries):
    current_rates()
    with django_assert_num_queries(0):
        assert current_rates()["USD"].value == Decimal("45.4274")


# Generated with AI
def test_a_saved_rate_clears_the_cache(rates, django_capture_on_commit_callbacks):
    current_rates()  # cached
    with django_capture_on_commit_callbacks(execute=True):
        ExchangeRate.objects.filter(currency="USD").update(rate=1)  # no signal
        add_rate("USD", "47.00", TODAY - timedelta(days=5))  # a signal

    assert current_rates()["USD"].value == 1  # read from the database again


# Generated with AI
def test_a_changed_currency_clears_the_cache(rates, django_capture_on_commit_callbacks):
    assert [currency.code for currency in available_currencies()] == ["UAH", "EUR", "USD"]
    with django_capture_on_commit_callbacks(execute=True):
        Currency.objects.create(code="PLN", name="Zloty", symbol="zł")
        add_rate("PLN", "11.2")

    assert [currency.code for currency in available_currencies()] == ["UAH", "EUR", "PLN", "USD"]


# Generated with AI
@pytest.mark.parametrize(
    "amount, from_code, to_code, expected",
    [
        ("650.00", "UAH", "USD", "14.31"),  # 650 / 45.4274 = 14.3085...
        ("20.00", "USD", "UAH", "908.55"),  # 20 * 45.4274 = 908.548
        ("20.00", "USD", "EUR", "18.05"),  # 20 * 45.4274 / 50.3379 = 18.0489...
        ("650.00", "UAH", "UAH", "650.00"),
    ],
)
def test_convert(rates, amount, from_code, to_code, expected):
    assert convert(Decimal(amount), from_code, to_code) == Decimal(expected)


# Generated with AI
def test_convert_rounds_half_up():
    add_rate("USD", "2")
    # 0.05 UAH / 2 = 0.025 USD -> 0.03 (banker's rounding would give 0.02)
    assert convert(Decimal("0.05"), "UAH", "USD") == Decimal("0.03")


# Generated with AI
def test_cross_rate_is_not_rounded(rates):
    assert cross_rate("USD", "EUR") == Decimal("45.4274") / Decimal("50.3379")


# Generated with AI
def test_convert_without_a_rate_fails():
    with pytest.raises(RateUnavailable, match="USD"):
        convert(Decimal("10"), "UAH", "USD")


# ---------------------------------------------------------------------------
# NBU client
# ---------------------------------------------------------------------------


# Generated with AI
def test_fetch_rates_reads_exact_decimals(nbu_answer):
    published = nbu.fetch_rates(date(2026, 11, 14))

    assert published["USD"] == nbu.PublishedRate(Decimal("45.4274"), date(2026, 11, 17))
    assert str(published["PLN"].rate) == "11.2"  # from the text, not from a float
    assert nbu_answer.requests == [
        {"url": nbu.URL, "params": {"json": "", "date": "20261114"}, "timeout": nbu.TIMEOUT}
    ]


# Generated with AI
def test_fetch_rates_without_a_date_asks_for_the_newest(nbu_answer):
    nbu.fetch_rates()

    assert nbu_answer.requests[0]["params"] == {"json": ""}


# Generated with AI
@pytest.mark.parametrize(
    "body",
    [
        "<html>Service unavailable</html>",  # not JSON
        '{"message": "error"}',  # JSON of another shape
        '[{"cc": "USD", "rate": 45.4, "exchangedate": "2026-11-17"}]',  # another date format
    ],
)
def test_a_strange_answer_is_an_nbu_error(nbu_answer, body):
    nbu_answer.body = body
    with pytest.raises(nbu.NBUError):
        nbu.fetch_rates()


# Generated with AI
def test_an_http_error_is_raised_as_it_is(nbu_answer):
    nbu_answer.status = 503
    # requests.HTTPError is an OSError: the Celery task retries it
    with pytest.raises(requests.HTTPError):
        nbu.fetch_rates()
    assert issubclass(requests.HTTPError, OSError)


# ---------------------------------------------------------------------------
# The update
# ---------------------------------------------------------------------------


# Generated with AI
def test_update_saves_the_rates_of_the_active_currencies(nbu_answer):
    result = update_rates()

    assert result.date == date(2026, 11, 17)  # the date from the NBU
    assert result.saved == {"USD": Decimal("45.4274"), "EUR": Decimal("50.3379")}
    # PLN is published, but not a currency of the shop
    assert set(ExchangeRate.objects.values_list("currency", "date", "rate", "source")) == {
        ("USD", date(2026, 11, 17), Decimal("45.427400"), "nbu"),
        ("EUR", date(2026, 11, 17), Decimal("50.337900"), "nbu"),
    }


# Generated with AI
def test_update_twice_changes_nothing(nbu_answer):
    update_rates()
    update_rates()

    assert ExchangeRate.objects.count() == 2


# Generated with AI
def test_update_takes_the_corrected_nbu_rate(nbu_answer):
    add_rate("USD", "40.00", date(2026, 11, 17))

    update_rates()

    assert ExchangeRate.objects.get(currency="USD").rate == Decimal("45.4274")


# Generated with AI
def test_update_keeps_a_manual_rate(nbu_answer):
    add_rate("EUR", "51.00", date(2026, 11, 17), source=ExchangeRate.Source.MANUAL)

    result = update_rates()

    assert result.kept_manual == ["EUR"]
    assert ExchangeRate.objects.get(currency="EUR").rate == Decimal("51.00")


# Generated with AI
def test_update_skips_turned_off_currencies_and_reports_missing_ones(nbu_answer, caplog):
    Currency.objects.filter(code="EUR").update(is_active=False)
    Currency.objects.create(code="XYZ", name="Unknown", symbol="X")

    result = update_rates()

    assert list(result.saved) == ["USD"]
    assert result.missing == ["XYZ"]
    assert "NBU rates for 17.11.2026: no rate for XYZ" in caplog.text


# Generated with AI
def test_update_with_an_empty_answer_saves_nothing(nbu_answer):
    nbu_answer.body = "[]"
    with pytest.raises(nbu.NBUError):
        update_rates()
    assert not ExchangeRate.objects.exists()


# ---------------------------------------------------------------------------
# Command, task, schedule
# ---------------------------------------------------------------------------


# Generated with AI
def test_command_prints_the_saved_rates(nbu_answer, capsys):
    add_rate("EUR", "51.00", date(2026, 11, 17), source=ExchangeRate.Source.MANUAL)

    call_command("update_exchange_rates", "--date", "2026-11-14")

    output = capsys.readouterr().out
    assert nbu_answer.requests[0]["params"]["date"] == "20261114"
    # The output is in the language of the site (Ukrainian by default)
    assert "USD на 17.11.2026: 45.4274 грн" in output
    assert "EUR на 17.11.2026: залишено ручний курс" in output
    assert "Збережено: 1." in output


# Generated with AI
def test_command_reports_a_missing_rate(nbu_answer, capsys):
    Currency.objects.create(code="XYZ", name="Unknown", symbol="X")

    call_command("update_exchange_rates")

    assert "XYZ: у НБУ немає курсу на 17.11.2026" in capsys.readouterr().out


# Generated with AI
def test_command_fails_clearly_when_the_nbu_is_down(nbu_answer):
    nbu_answer.status = 503
    with pytest.raises(CommandError, match="Не вдалося завантажити курси НБУ"):
        call_command("update_exchange_rates")


# Generated with AI
def test_task_returns_a_summary(nbu_answer):
    result = update_exchange_rates.delay()

    # The NBU had nothing newer than "today" (both answers are 17.11): one day
    assert result.get() == [
        {
            "date": "2026-11-17",
            "saved": {"USD": "45.4274", "EUR": "50.3379"},
            "kept_manual": [],
            "missing": [],
        }
    ]


# Generated with AI
def test_without_a_date_today_and_the_newest_day_are_loaded(nbu_answer, capsys):
    # 16.11 in the afternoon: the NBU already has the rates of the 17th.
    # Only them would leave today (16.11) without a rate.
    nbu_answer.follow_date = True

    call_command("update_exchange_rates")

    assert [request["params"] for request in nbu_answer.requests] == [
        {"json": "", "date": "20261116"},
        {"json": ""},
    ]
    assert sorted(ExchangeRate.objects.values_list("currency", "date")) == [
        ("EUR", date(2026, 11, 16)),
        ("EUR", date(2026, 11, 17)),
        ("USD", date(2026, 11, 16)),
        ("USD", date(2026, 11, 17)),
    ]
    output = capsys.readouterr().out
    assert "USD на 16.11.2026: 45.4274 грн" in output
    assert "USD на 17.11.2026: 45.4274 грн" in output
    assert current_rates()["USD"].date == TODAY


# Generated with AI
def test_task_retries_when_the_nbu_is_down(nbu_answer):
    nbu_answer.status = 503

    result = update_exchange_rates.delay()

    assert len(nbu_answer.requests) == 1 + 3  # the first try + 3 retries
    assert result.failed()


# Generated with AI
def test_task_does_not_retry_a_strange_answer(nbu_answer):
    nbu_answer.body = '{"message": "error"}'

    result = update_exchange_rates.delay()

    assert len(nbu_answer.requests) == 1
    assert result.failed()


# Generated with AI
def test_rates_are_updated_every_afternoon_and_in_the_morning(settings):
    entry = settings.CELERY_BEAT_SCHEDULE["update-exchange-rates"]

    assert entry["task"] in celery_app.tasks
    assert entry["schedule"].hour == {6, 13, 14, 15, 16, 17}
    assert entry["schedule"].minute == {5}


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


# Generated with AI
def test_admin_currency_list_shows_the_current_rate(admin_client, rates):
    response = admin_client.get(reverse("admin:currencies_currency_changelist"))

    assert response.status_code == 200
    # The admin is in Ukrainian by default: a decimal comma
    assert "45,427400" in response.text


# Generated with AI
def test_admin_currency_code_is_read_only_after_adding(admin_client):
    response = admin_client.get(reverse("admin:currencies_currency_change", args=["USD"]))

    assert 'name="code"' not in response.text
    assert 'name="name"' in response.text


# Generated with AI
def test_admin_rate_is_saved_as_manual(admin_client):
    url = reverse("admin:currencies_exchangerate_add")

    form = admin_client.get(url).text
    response = admin_client.post(url, {"currency": "USD", "date": "2026-11-16", "rate": "46.5"})

    assert 'value="UAH"' not in form  # the base currency is not offered
    assert response.status_code == 302
    rate = ExchangeRate.objects.get()
    assert (rate.currency_id, rate.rate, rate.source) == ("USD", Decimal("46.5"), "manual")


# ---------------------------------------------------------------------------
# The "NBU rates" page: load, check, save with a button
# ---------------------------------------------------------------------------

RATES_URL = "/currencies/rates/"


def snapshot_of(response):
    """The signed NBU answer the page put into its form."""
    return response.context["form"]["snapshot"].value()


def test_rates_page_is_only_for_who_may_change_rates(client, customer_client, manager_client):
    # Anonymous: to the login page; logged in without the right: 403
    assert client.get(RATES_URL).status_code == 302
    assert customer_client.get(RATES_URL).status_code == 403
    assert manager_client.get(RATES_URL).status_code == 403


def test_rates_page_shows_the_nbu_numbers_and_saves_nothing(superuser_client, nbu_answer):
    add_rate("USD", "45.1", day=date(2026, 11, 17), source=ExchangeRate.Source.MANUAL)

    response = superuser_client.get(RATES_URL)

    assert response.status_code == 200
    assert response.context["rate_date"] == date(2026, 11, 17)
    rows = {
        currency.code: (nbu_value, saved)
        for currency, _, nbu_value, saved in response.context["rows"]
    }
    assert rows["USD"][0] == Decimal("45.4274")
    assert rows["USD"][1].rate == Decimal("45.1")  # the saved manual rate is shown
    assert rows["EUR"] == (Decimal("50.3379"), None)
    assert "PLN" not in rows  # not a currency of the shop
    html = response.content.decode()
    assert 'data-nbu="45.4274"' in html
    assert "Курси НБУ" in html
    # Only shown, nothing saved yet
    assert ExchangeRate.objects.count() == 1


def test_rates_page_asks_the_nbu_for_the_chosen_day(superuser_client, nbu_answer):
    nbu_answer.follow_date = True

    response = superuser_client.get(RATES_URL, {"date": "2026-11-10"})

    assert nbu_answer.requests[-1]["params"]["date"] == "20261110"
    assert response.context["rate_date"] == date(2026, 11, 10)


def test_unchanged_rate_is_nbu_changed_is_manual_empty_is_skipped(superuser_client, nbu_answer):
    snapshot = snapshot_of(superuser_client.get(RATES_URL))

    response = superuser_client.post(
        RATES_URL, {"snapshot": snapshot, "rate_USD": "45.427400", "rate_EUR": "50.5"}
    )

    assert response.status_code == 302
    assert response.url == f"{RATES_URL}?date=2026-11-17"
    saved = {r.currency_id: (r.rate, r.source) for r in ExchangeRate.objects.all()}
    # 45.427400 == 45.4274: the NBU number -> "nbu"
    assert saved == {
        "USD": (Decimal("45.4274"), ExchangeRate.Source.NBU),
        "EUR": (Decimal("50.5"), ExchangeRate.Source.MANUAL),
    }
    page = superuser_client.get(response.url)
    assert "Курси на 17.11.2026 збережено: EUR (Вручну), USD (НБУ)." in page.content.decode()


def test_an_empty_field_leaves_the_rate_as_it_is(superuser_client, nbu_answer):
    add_rate("EUR", "49", day=date(2026, 11, 17))
    snapshot = snapshot_of(superuser_client.get(RATES_URL))

    superuser_client.post(RATES_URL, {"snapshot": snapshot, "rate_USD": "45.4274", "rate_EUR": ""})

    assert ExchangeRate.objects.get(currency_id="EUR").rate == Decimal("49")


def test_confirmed_nbu_number_replaces_a_manual_rate(superuser_client, nbu_answer):
    """The person saw both numbers and kept the NBU one: it is "nbu" again."""
    add_rate("USD", "45.1", day=date(2026, 11, 17), source=ExchangeRate.Source.MANUAL)
    snapshot = snapshot_of(superuser_client.get(RATES_URL))

    superuser_client.post(RATES_URL, {"snapshot": snapshot, "rate_USD": "45.4274"})

    rate = ExchangeRate.objects.get(currency_id="USD")
    assert (rate.rate, rate.source) == (Decimal("45.4274"), ExchangeRate.Source.NBU)


def test_a_forged_snapshot_saves_nothing(superuser_client, nbu_answer):
    """The NBU numbers in the hidden field are signed: another number -> "out of date"."""
    snapshot = snapshot_of(superuser_client.get(RATES_URL))

    response = superuser_client.post(
        RATES_URL, {"snapshot": snapshot[:-3] + "abc", "rate_USD": "1"}, follow=True
    )

    assert not ExchangeRate.objects.exists()
    assert "Сторінка застаріла" in response.content.decode()


def test_a_wrong_number_shows_the_form_again(superuser_client, nbu_answer):
    snapshot = snapshot_of(superuser_client.get(RATES_URL))

    response = superuser_client.post(RATES_URL, {"snapshot": snapshot, "rate_USD": "-5"})

    assert response.status_code == 200
    assert "rate_USD" in response.context["form"].errors
    assert not ExchangeRate.objects.exists()


@pytest.mark.parametrize(
    ("body", "status", "text"),
    [
        ("[]", 200, "У НБУ ще немає курсів на цей день."),
        ("Service Unavailable", 503, "НБУ не відповів."),
        ('{"error": "bad"}', 200, "НБУ не відповів."),
    ],
)
def test_rates_page_when_the_nbu_has_nothing(superuser_client, nbu_answer, body, status, text):
    nbu_answer.body, nbu_answer.status = body, status

    response = superuser_client.get(RATES_URL)

    assert response.status_code == 200
    assert response.context["form"] is None
    assert text in response.content.decode()


def test_rates_page_wrong_date(superuser_client, nbu_answer):
    response = superuser_client.get(RATES_URL, {"date": "16.11.2026"})

    assert "Неправильна дата" in response.content.decode()
    assert nbu_answer.requests == []


def test_profile_links_to_the_rates_page_only_with_the_right(superuser_client, customer_client):
    assert RATES_URL in superuser_client.get(reverse("users:profile")).content.decode()
    assert RATES_URL not in customer_client.get(reverse("users:profile")).content.decode()
