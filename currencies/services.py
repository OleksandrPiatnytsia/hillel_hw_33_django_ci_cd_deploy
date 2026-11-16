"""Current exchange rates, conversion between currencies, the NBU update.

    current_rates()            {"UAH": Rate(1, None), "USD": Rate(45.4274, 2026-11-16), ...}
    convert(650, "UAH", "USD") Decimal("14.31")
    update_rates()             load the rates from the NBU into ExchangeRate

Every rate is "how many UAH for 1 unit" (currencies/models.py), so any
conversion goes through the hryvnia:

    650 UAH -> USD:   650 * 1 / 45.4274        = 14.3085... -> 14.31
    20 USD  -> EUR:   20 * 45.4274 / 50.3379   = 18.0489... -> 18.05

Only the result is rounded (to 0.01, ROUND_HALF_UP), never the rates in
between: rounding twice could be one cent off.

"Today" is the date in Kyiv, not in UTC (TIME_ZONE of the site): the NBU
sets its rates for Kyiv days. At 23:30 UTC on 16.11 it is already 17.11
in Kyiv, and the rate of the 17th is the one in force.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.db import transaction
from django.db.models import Case, DecimalField, F, Value, When
from django.db.models.functions import Round
from django.utils import timezone

from . import nbu
from .models import BASE_CURRENCY, Currency, ExchangeRate

# Logs (logger "currencies.services"):
#   INFO     NBU rates for 17.11.2026: saved USD 45.4274, EUR 50.3379
#   INFO     NBU rates for 17.11.2026: kept the manual rate of EUR
#   WARNING  NBU rates for 17.11.2026: no rate for XYZ
logger = logging.getLogger(__name__)

KYIV = ZoneInfo("Europe/Kyiv")
CENT = Decimal("0.01")

# The current rates are read on almost every page (prices in the catalog,
# the cart), so they are cached. The key has the date in it: after
# midnight in Kyiv the key is new and the rates of the new day are read
# from the database. A saved / deleted rate clears the key at once
# (currencies/signals.py), so the timeout is only a safety net.
CACHE_KEY = "currencies:rates:{day}"
CACHE_TIMEOUT = 24 * 60 * 60


class RateUnavailable(Exception):
    """There is no rate for this currency (never loaded or entered)."""


@dataclass(frozen=True)
class Rate:
    # How many UAH for 1 unit
    value: Decimal
    # The day of the rate; None for UAH (the base has no rate rows)
    date: date | None


def today():
    """Today in Kyiv: the day whose NBU rates are in force now."""
    return timezone.now().astimezone(KYIV).date()


def _cache_key(day):
    return CACHE_KEY.format(day=day.isoformat())


def _load_rates(day):
    rates = {BASE_CURRENCY: Rate(Decimal("1"), None)}
    # The newest rate of every currency up to `day`, in one query:
    #   SELECT DISTINCT ON (currency_id) currency_id, rate, date
    #   FROM currencies_exchangerate WHERE date <= %s
    #   ORDER BY currency_id, date DESC
    # DISTINCT ON keeps the first row of every currency, and ORDER BY puts
    # the newest date first (PostgreSQL only, like the whole project).
    # Inactive currencies too: a book with a price in a currency that was
    # turned off still gets converted with its last known rate.
    newest = (
        ExchangeRate.objects.filter(date__lte=day)
        .order_by("currency_id", "-date")
        .distinct("currency_id")
        .values_list("currency_id", "rate", "date")
    )
    for code, value, rate_date in newest:
        rates[code] = Rate(value, rate_date)
    return rates


def current_rates():
    """{code: Rate} of every currency that has a rate today, UAH included."""
    day = today()
    key = _cache_key(day)
    rates = cache.get(key)
    if rates is None:
        rates = _load_rates(day)
        cache.set(key, rates, CACHE_TIMEOUT)
    return rates


def clear_rates_cache():
    """Forget the cached rates of today and the cached currencies.

    The next current_rates() / all_currencies() reads them again.
    """
    cache.delete_many([_cache_key(today()), CURRENCIES_CACHE_KEY])


# All currencies, active or not: the symbol of a book's currency is needed
# on every page with prices, and a Currency row changes almost never.
# Cleared together with the rates (signals.py).
CURRENCIES_CACHE_KEY = "currencies:all"


def all_currencies():
    """{code: Currency} of every currency (inactive ones too), cached."""
    currencies = cache.get(CURRENCIES_CACHE_KEY)
    if currencies is None:
        currencies = {currency.code: currency for currency in Currency.objects.all()}
        cache.set(CURRENCIES_CACHE_KEY, currencies, CACHE_TIMEOUT)
    return currencies


def available_currencies():
    """The currencies offered on the site: active and with a rate today.

    UAH first (the base and the default), then the others by code.
    """
    with_rate = current_rates().keys()
    currencies = [
        currency
        for code, currency in all_currencies().items()
        if currency.is_active and code in with_rate
    ]
    return sorted(currencies, key=lambda currency: (not currency.is_base, currency.code))


def cross_rate(from_code, to_code, rates=None):
    """How many units of to_code for 1 unit of from_code (not rounded).

    rates: the result of current_rates(), when the caller already has it
    (a page converting 24 prices reads the cache once, not 24 times).
    """
    rates = current_rates() if rates is None else rates
    try:
        return rates[from_code].value / rates[to_code].value
    except KeyError as error:
        raise RateUnavailable(f"No exchange rate for {error.args[0]}") from None


def convert(amount, from_code, to_code, rates=None):
    """amount in from_code -> to_code, rounded to 0.01 (ROUND_HALF_UP)."""
    if from_code == to_code:
        return amount.quantize(CENT, ROUND_HALF_UP)
    return (amount * cross_rate(from_code, to_code, rates)).quantize(CENT, ROUND_HALF_UP)


def price_in(to_code, *, price="price", currency="currency", rates=None):
    """SQL expression: a price converted to to_code, for annotate / filter / order_by.

    Books have prices in different currencies, so "sort by price" or
    "price from 10 to 20 USD" needs the price in ONE currency, calculated
    by the database for every row. With the rates as constants (from
    current_rates(), no JOIN to the rates table):

        CASE WHEN currency_id = 'USD' THEN price
             WHEN currency_id = 'UAH' THEN ROUND(price * 0.022013..., 2)
             WHEN currency_id = 'EUR' THEN ROUND(price * 1.108096..., 2)
             ELSE NULL END

    ROUND(..., 2) in PostgreSQL rounds half away from zero, the same as
    convert() (ROUND_HALF_UP for prices >= 0): the number the database
    filters and sorts by is the number the page shows.
    A book in a currency without a rate gets NULL: a filter never matches
    it, ORDER BY puts it last (ascending) or first (descending).

    price / currency: the field names, also across relations, e.g.
    price="books__price", currency="books__currency" for Category.
    Raises RateUnavailable if to_code itself has no rate.
    """
    rates = current_rates() if rates is None else rates
    if to_code not in rates:
        raise RateUnavailable(f"No exchange rate for {to_code}")
    output = DecimalField(max_digits=14, decimal_places=2)
    whens = [When(**{currency: to_code}, then=F(price))]
    for code in rates:
        if code != to_code:
            factor = Value(cross_rate(code, to_code, rates))
            whens.append(When(**{currency: code}, then=Round(F(price) * factor, 2)))
    return Case(*whens, default=None, output_field=output)


# ---------------------------------------------------------------------------
# The update from the NBU (the update_exchange_rates command, Celery Beat)
# ---------------------------------------------------------------------------


@dataclass
class UpdateResult:
    # The day the NBU set the rates for (often tomorrow, see models.py)
    date: date
    saved: dict = field(default_factory=dict)  # {"USD": Decimal("45.4274")}
    kept_manual: list = field(default_factory=list)  # ["EUR"]: a manual rate wins
    missing: list = field(default_factory=list)  # ["XYZ"]: the NBU has no rate


def update_rates(day=None):
    """Load the NBU rates of `day` (default: the newest) for every active currency.

    A manual rate of the same day stays: somebody entered it on purpose
    (the NBU rate was wrong or late). Raises nbu.NBUError when the NBU is
    down or answers something unexpected: nothing is saved then, and the
    site keeps using the last known rates.
    """
    published = nbu.fetch_rates(day)
    if not published:
        raise nbu.NBUError("The NBU returned no rates")
    # One request = one day; the date comes from the NBU, not from `day`
    # (without `day` the NBU decides which day is the newest)
    rate_date = next(iter(published.values())).date
    result = UpdateResult(date=rate_date)

    codes = Currency.objects.filter(is_active=True).exclude(code=BASE_CURRENCY)
    with transaction.atomic():
        for code in codes.values_list("code", flat=True):
            if code not in published:
                result.missing.append(code)
                continue
            source = (
                ExchangeRate.objects.filter(currency_id=code, date=rate_date)
                .values_list("source", flat=True)
                .first()
            )
            if source == ExchangeRate.Source.MANUAL:
                result.kept_manual.append(code)
                continue
            value = published[code].rate
            # update_or_create: the row of this day is new (INSERT) or the
            # NBU corrected its rate (UPDATE). It locks the row it updates
            # (SELECT ... FOR UPDATE), and if another run (the hourly Beat
            # task and a manual command at the same time) inserts the same
            # row first, it catches the IntegrityError and updates instead.
            ExchangeRate.objects.update_or_create(
                currency_id=code,
                date=rate_date,
                defaults={"rate": value, "source": ExchangeRate.Source.NBU},
            )
            result.saved[code] = value

    day_text = f"{rate_date:%d.%m.%Y}"
    if result.saved:
        saved = ", ".join(f"{code} {value}" for code, value in result.saved.items())
        logger.info("NBU rates for %s: saved %s", day_text, saved)
    for code in result.kept_manual:
        logger.info("NBU rates for %s: kept the manual rate of %s", day_text, code)
    for code in result.missing:
        logger.warning("NBU rates for %s: no rate for %s", day_text, code)
    return result


def update_current_rates():
    """The rates of today AND the newest ones: [UpdateResult, ...].

    After ~15:30 Kyiv time the newest NBU rates are the ones of tomorrow.
    Loading only them (the first run after a deploy, or after the NBU was
    down for a day) would leave today without a rate: the site would offer
    only UAH until midnight. So today is loaded first, then the newest day
    if it is another one (two requests; the second is skipped when the NBU
    has nothing newer than today).
    """
    results = [update_rates(today())]
    newest = update_rates()
    if newest.date != results[0].date:
        results.append(newest)
    return results


# ---------------------------------------------------------------------------
# The update with a confirmation (the "NBU rates" page of the site)
# ---------------------------------------------------------------------------


def save_confirmed_rates(rate_date, values, published, *, user=None):
    """Save the rates a staff member confirmed: {code: "nbu" | "manual"}.

    values:    {"USD": Decimal("45.4274"), ...} — what the form sent; a
               currency without a value is skipped (left as it is)
    published: {"USD": Decimal("45.4274"), ...} — what the NBU gave when
               the page was opened

    A value equal to the NBU one is saved as "nbu", even over a manual rate
    of the day: the person saw both and chose the NBU number. A changed
    value (or a rate the NBU doesn't have) is "manual", and the automatic
    update keeps it (update_rates). Equal as numbers: 45.4274 == 45.427400.
    All in one transaction: either every confirmed rate or none.
    """
    sources = {}
    with transaction.atomic():
        for code, value in values.items():
            if value is None:
                continue
            nbu_value = published.get(code)
            source = (
                ExchangeRate.Source.NBU
                if nbu_value is not None and value == nbu_value
                else ExchangeRate.Source.MANUAL
            )
            ExchangeRate.objects.update_or_create(
                currency_id=code,
                date=rate_date,
                defaults={"rate": value, "source": source},
            )
            sources[code] = source

    if sources:
        saved = ", ".join(f"{code} {values[code]} ({source})" for code, source in sources.items())
        logger.info(
            "Rates for %s confirmed by %s: %s",
            f"{rate_date:%d.%m.%Y}",
            getattr(user, "username", "?"),
            saved,
        )
    return sources
