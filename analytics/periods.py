"""The period of the page /analytics/: the same rules as in Analytics.

    ?period=7|30|90            the last N days, today included (30 by default)
    ?from=YYYY-MM-DD&to=YYYY-MM-DD   any days, at most 366

"Today" is a day in Kyiv (ANALYTICS_TIME_ZONE): Analytics counts its report
days in Kyiv, so "the last 7 days" here and there end with the same day.
Analytics is always asked with the real dates (?from=&to=): the cached
answer of "30 days" must not be shown tomorrow for another 30 days.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext

PRESETS = (7, 30, 90)
DEFAULT_PRESET = 30
MAX_DAYS = 366


class PeriodError(ValueError):
    """A wrong period in the query: the message is shown on the page."""


@dataclass(frozen=True)
class Period:
    first: date
    last: date
    preset: int | None = None  # 7 / 30 / 90, None for chosen dates

    @property
    def days(self):
        return (self.last - self.first).days + 1

    @property
    def query(self):
        """The parameters of Analytics' report API."""
        return {"from": self.first.isoformat(), "to": self.last.isoformat()}


def today():
    return timezone.localdate(timezone=ZoneInfo(settings.ANALYTICS_TIME_ZONE))


def last_days(days):
    last = today()
    return Period(first=last - timedelta(days=days - 1), last=last, preset=days)


def parse_period(query):
    """request.GET -> Period, or PeriodError with a translated reason."""
    first, last = query.get("from", ""), query.get("to", "")
    if first or last:
        if not (first and last):
            raise PeriodError(gettext("Choose both dates of the period."))
        try:
            first, last = date.fromisoformat(first), date.fromisoformat(last)
        except ValueError as error:
            raise PeriodError(gettext("A date of the period is not a valid date.")) from error
        if first > last:
            raise PeriodError(gettext("The start of the period is later than its end."))
        if (last - first).days + 1 > MAX_DAYS:
            raise PeriodError(
                gettext("The period is longer than %(days)s days.") % {"days": MAX_DAYS}
            )
        return Period(first=first, last=last)

    preset = query.get("period", "")
    if not preset:
        return last_days(DEFAULT_PRESET)
    if not preset.isdigit() or int(preset) not in PRESETS:
        raise PeriodError(gettext("Unknown period: choose 7, 30 or 90 days."))
    return last_days(int(preset))
