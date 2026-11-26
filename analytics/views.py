"""/analytics/: the sales of the shop from the reports of the Analytics service.

    AnalyticsBaseView      the right orders.view_sales_analytics (Managers),
      (PermissionRequiredMixin   the period (?period= or ?from=&to=), one
       + TemplateView)           client for all the reports of the page, the
                                 caches, the messages when Analytics is down
      SalesAnalyticsView   which reports (summary, daily, top books,
                           formats) and how to show them: tiles, the chart,
                           the books of this shop with their stock

Another page of reports = a subclass with its own `reports` and prepare().

Analytics down: the page still answers 200. It shows the last good numbers
with their time, or a message without numbers; the client has logged why.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.utils.dateparse import parse_date
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from books.models import LOW_STOCK_THRESHOLD, Book, BookFormat

from .client import AnalyticsClient
from .periods import DEFAULT_PRESET, PRESETS, PeriodError, last_days, parse_period
from .reports import NOT_CONFIGURED, REFUSED, UNAVAILABLE, fetch_report

logger = logging.getLogger(__name__)  # "analytics.views"


class AnalyticsBaseView(PermissionRequiredMixin, TemplateView):
    # Anonymous -> the login page, logged in without the right -> 403
    permission_required = "orders.view_sales_analytics"
    # name of the report in Analytics -> its extra parameters
    reports = {}

    def get_client(self):
        return AnalyticsClient()

    def get_period(self):
        """(period, error): a wrong query shows the default period and the reason."""
        try:
            return parse_period(self.request.GET), ""
        except PeriodError as error:
            return last_days(DEFAULT_PRESET), str(error)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period, period_error = self.get_period()
        # One client for the page: after the first failure the others fail
        # at once (the client remembers it), the page doesn't wait 4 times
        client = self.get_client()
        results = {
            name: fetch_report(name, period, client, **params)
            for name, params in self.reports.items()
        }
        problems = {result.problem for result in results.values() if result.problem}
        stale_times = [result.fetched_at for result in results.values() if result.stale]
        if problems - {NOT_CONFIGURED}:
            logger.warning(
                "Analytics page for %s shown without fresh data: %s",
                self.request.user.username,
                ", ".join(sorted(problems)),
            )
        context.update(
            period=period,
            period_error=period_error,
            presets=PRESETS,
            results=results,
            not_configured=NOT_CONFIGURED in problems,
            unavailable=UNAVAILABLE in problems,
            refused=REFUSED in problems,
            # The oldest of the shown copies: "the numbers as of 14:05"
            stale_since=min(stale_times) if stale_times else None,
            analytics_url=settings.ANALYTICS_PUBLIC_URL,
        )
        context.update(self.prepare({name: result.data for name, result in results.items()}))
        return context

    def prepare(self, data):
        """Extra context from the answers (None = no answer). For the subclasses."""
        return {}


@dataclass
class Tile:
    """One number of the summary: value, change against the previous period."""

    label: str
    value: Decimal
    kind: str  # "money" | "percent" | "count"
    change: Decimal | None  # %, None when the previous period had 0
    # True: a growth is good (revenue); False: a growth is bad (cancellations)
    higher_is_better: bool = True

    @property
    def good(self):
        if not self.change:
            return None
        return (self.change > 0) == self.higher_is_better


# The values of the contract of Analytics -> the labels of this shop
FORMAT_LABELS = {
    "paper": BookFormat.FormatType.PAPER.label,
    "ebook": BookFormat.FormatType.EBOOK.label,
    "audio": BookFormat.FormatType.AUDIOBOOK.label,
}


def number(value):
    """A number of the JSON (money comes as the string "1234.50") -> Decimal."""
    return Decimal(str(value)) if value is not None else None


class SalesAnalyticsView(AnalyticsBaseView):
    template_name = "analytics/sales.html"
    reports = {"summary": {}, "daily": {}, "top-books": {"limit": 10}, "formats": {}}

    # (key of the totals, label, kind, a growth is good)
    TILES = [
        ("revenue_uah", _("Revenue"), "money", True),
        ("orders", _("Orders"), "count", True),
        ("average_order_uah", _("Average order"), "money", True),
        ("paid_share", _("Paid"), "percent", True),
        ("cancelled_share", _("Cancelled"), "percent", False),
        ("new_customers", _("New customers"), "count", True),
    ]

    def prepare(self, data):
        return {
            "tiles": self.tiles(data["summary"]),
            "days": self.days(data["daily"]),
            "chart": self.chart(data["daily"]),
            "top_books": self.top_books(data["top-books"]),
            "formats": self.formats(data["formats"]),
            "low_stock_threshold": LOW_STOCK_THRESHOLD,
        }

    def tiles(self, summary):
        if summary is None:
            return []
        totals, changes = summary["totals"], summary.get("changes", {})
        return [
            Tile(label, number(totals[key]), kind, number(changes.get(key)), better)
            for key, label, kind, better in self.TILES
        ]

    def days(self, daily):
        if daily is None:
            return []
        return [
            {
                "day": parse_date(day["day"]),
                "orders": day["orders"],
                "revenue": number(day["revenue_uah"]),
            }
            for day in daily["days"]
        ]

    def chart(self, daily):
        """The data of the revenue chart for json_script (static/js/analytics.js)."""
        days = self.days(daily)
        if not days:
            return None
        return {
            "labels": [date_format(day["day"], "d.m") for day in days],
            # Strings: JSON numbers would be floats; Chart.js parses them
            "revenue": [str(day["revenue"]) for day in days],
            "orders": [day["orders"] for day in days],
            "revenue_label": str(_("Revenue, UAH")),
            "orders_label": str(_("Orders")),
        }

    def top_books(self, answer):
        """The books of Analytics + the same books of this shop (link, stock now).

        None = no answer (no table at all), [] = no sales (an empty table)."""
        if answer is None:
            return None
        rows = answer["books"]
        # One query for the 10 books; a book deleted here since stays a line
        # without a link
        books = Book.objects.with_stock().in_bulk([row["source_id"] for row in rows])
        return [
            {
                "book": books.get(row["source_id"]),
                "title": row["title"],
                "author": row["author"],
                "quantity": row["quantity"],
                "revenue": number(row["revenue_uah"]),
            }
            for row in rows
        ]

    def formats(self, answer):
        if answer is None:
            return None
        return [
            {
                "label": FORMAT_LABELS.get(row["format_type"], row["format_type"]),
                "quantity": row["quantity"],
                "revenue": number(row["revenue_uah"]),
                "share": number(row["revenue_share"]),
            }
            for row in answer["formats"]
        ]
