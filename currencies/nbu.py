"""Client of the NBU exchange rates API (National Bank of Ukraine).

    GET https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json=&date=20261116

    [{"r030": 840, "txt": "Долар США", "rate": 45.4274, "cc": "USD",
      "exchangedate": "16.11.2026", "special": "N"}, ...]

- no key, no account; one request returns all ~45 currencies of one day;
- "rate" is how many UAH for 1 unit, like ExchangeRate.rate;
- without &date= the NBU returns the newest rates: after ~15:30 Kyiv time
  that is already the rate of the next working day;
- weekends and holidays have rates too (the same as the day before).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import requests

URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
# Seconds to wait for the NBU; the Celery task retries a timeout later
TIMEOUT = 10


class NBUError(Exception):
    """The NBU answered something that is not a list of rates."""


@dataclass(frozen=True)
class PublishedRate:
    rate: Decimal  # UAH for 1 unit
    date: date


def fetch_rates(day=None):
    """{"USD": PublishedRate(Decimal("45.4274"), date(2026, 11, 16)), ...}

    day: the rates of this day; None -> the newest ones.
    Network errors (requests.RequestException: no connection, timeout,
    HTTP 5xx) are raised as they are: they are OSError, and the Celery task
    retries every OSError. A broken answer raises NBUError.
    """
    params = {"json": ""}
    if day is not None:
        params["date"] = day.strftime("%Y%m%d")
    response = requests.get(URL, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    try:
        # parse_float=Decimal: 45.4274 becomes Decimal("45.4274") straight
        # from the text, never the float 45.427399999999...
        items = response.json(parse_float=Decimal)
        return {
            item["cc"]: PublishedRate(
                rate=Decimal(item["rate"]),
                date=datetime.strptime(item["exchangedate"], "%d.%m.%Y").date(),
            )
            for item in items
        }
    except (ValueError, KeyError, TypeError) as error:
        # ValueError: not JSON, or a date in another format;
        # KeyError / TypeError: JSON of another shape (an error object)
        raise NBUError(f"Unexpected answer of the NBU: {error!r}") from error
