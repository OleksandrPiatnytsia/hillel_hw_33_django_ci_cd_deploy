"""The reports of Analytics with two caches: a fresh one and the last good one.

    result = fetch_report("summary", period, client)
    result.data         the JSON of Analytics, or None
    result.fetched_at   when Analytics gave it
    result.stale        True: Analytics is down, this is the last good answer
    result.problem      "" | "not_configured" | "unavailable" | "refused"

    fresh copy        ANALYTICS_CACHE_TIMEOUT (5 minutes): the page doesn't
                      call Analytics on every view; Analytics recalculates
                      its days every 10 minutes anyway
    last good copy    ANALYTICS_STALE_TIMEOUT (24 hours): shown with its
                      time while Analytics is down, instead of an empty page

The keys hold the real dates of the period ("2026-11-01..2026-11-30"), not
"period=30": tomorrow "the last 30 days" is another period.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .client import AnalyticsNotConfigured, AnalyticsRefused, AnalyticsUnavailable

logger = logging.getLogger(__name__)  # "analytics.reports"

# The report API of Analytics (reports/api.py there)
REPORT_PATHS = {
    "summary": "/api/reports/summary/",
    "daily": "/api/reports/daily/",
    "top-books": "/api/reports/top-books/",
    "formats": "/api/reports/formats/",
}

NOT_CONFIGURED = "not_configured"
UNAVAILABLE = "unavailable"
REFUSED = "refused"


@dataclass
class ReportResult:
    data: dict | None = None
    fetched_at: datetime | None = None
    stale: bool = False
    problem: str = ""


def cache_key(name, query):
    parameters = "&".join(f"{key}={value}" for key, value in sorted(query.items()))
    return f"analytics:report:{name}:{parameters}"


def fetch_report(name, period, client, **params):
    """One report of the period, from the cache or from Analytics. Never raises."""
    query = {**period.query, **params}
    key = cache_key(name, query)
    fresh = cache.get(key)
    if fresh is not None:
        return ReportResult(data=fresh["data"], fetched_at=fresh["fetched_at"])

    try:
        data = client.get(REPORT_PATHS[name], query)
    except AnalyticsNotConfigured:
        return ReportResult(problem=NOT_CONFIGURED)
    except (AnalyticsUnavailable, AnalyticsRefused) as error:
        # The client logged the reason already
        problem = UNAVAILABLE if isinstance(error, AnalyticsUnavailable) else REFUSED
        last_good = cache.get(f"{key}:last-good")
        if last_good is None:
            return ReportResult(problem=problem)
        return ReportResult(
            data=last_good["data"],
            fetched_at=last_good["fetched_at"],
            stale=True,
            problem=problem,
        )

    entry = {"data": data, "fetched_at": timezone.now()}
    cache.set(key, entry, settings.ANALYTICS_CACHE_TIMEOUT)
    cache.set(f"{key}:last-good", entry, settings.ANALYTICS_STALE_TIMEOUT)
    logger.debug("Analytics report %s fetched: %s", name, query)
    return ReportResult(data=data, fetched_at=entry["fetched_at"])
