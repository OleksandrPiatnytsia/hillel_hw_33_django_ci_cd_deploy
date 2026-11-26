"""The low stock report for the "Managers" group (Celery Beat, every morning).

    report = build_low_stock_report()
    report.books        paper books with 0..LOW_STOCK_THRESHOLD copies NOW
    report.csv_files()  -> [("low_stock_2026-11-25.csv", b"...")]
    send_low_stock_report_email(report)

The sales (orders, revenue, best sellers) are not here any more: they are
in the daily email of the Analytics service to its Analysts, and on the
page /analytics/ of this shop. The stock is a matter of this shop only.

day_bounds() is used by the backfill API too (api/views/analytics.py).
"""

import csv
import io
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone, translation

from books.models import LOW_STOCK_THRESHOLD, Book, BookFormat
from users.models import User

logger = logging.getLogger(__name__)  # "orders.reports"

MANAGERS_GROUP = "Managers"


@dataclass
class LowStockReport:
    day: object  # datetime.date: the day of the email
    books: list  # Book objects with .stock (with_stock())

    def csv_files(self):
        """[(file name, bytes), ...] for EmailMessage.attach()."""
        return [
            (
                f"low_stock_{self.day.isoformat()}.csv",
                _csv(
                    ["book_id", "title", "author", "stock"],
                    [[b.pk, b.title, b.author.name, b.stock] for b in self.books],
                ),
            )
        ]


def _csv(header, rows):
    """CSV as bytes. utf-8-sig: the BOM at the start tells Excel the file
    is UTF-8, otherwise Ukrainian titles come out as "РљРѕР±Р·Р°СЂ"."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def day_bounds(day):
    """[start, end) of a calendar day in TIME_ZONE as aware datetimes."""
    start = timezone.make_aware(datetime.combine(day, time.min))
    return start, start + timedelta(days=1)


def build_low_stock_report():
    # Only the books sold on paper: an e-book has no copies to order more of
    books = list(
        Book.objects.with_stock()
        .select_related("author")
        .filter(
            formats__format_type=BookFormat.FormatType.PAPER,
            formats__is_active=True,
            stock__lte=LOW_STOCK_THRESHOLD,
        )
        .order_by("stock", "title")
    )
    return LowStockReport(day=timezone.localdate(), books=books)


def send_low_stock_report_email(report):
    """One email per language of the managers, with the CSV file attached.

    Nothing to report (every paper book has enough copies) -> no email: a
    daily "all is fine" teaches the managers to skip the email.
    Raises on an SMTP / network error: the Celery task retries it (a retry
    may send the email again to the languages already done: a duplicate
    report is better than none). Returns the number of recipients.
    """
    if not report.books:
        logger.info("Low stock report %s: every paper book has enough copies", report.day)
        return 0
    managers = User.objects.filter(groups__name=MANAGERS_GROUP, is_active=True).exclude(email="")
    by_language = {}
    for manager in managers:
        by_language.setdefault(manager.language, []).append(manager.email)
    if not by_language:
        logger.warning("Low stock report %s: no active managers with an email", report.day)
        return 0

    attachments = report.csv_files()
    for language, emails in by_language.items():
        with translation.override(language):
            context = {
                "report": report,
                "threshold": LOW_STOCK_THRESHOLD,
                "site_url": settings.SITE_URL,
                "analytics_url": settings.ANALYTICS_PUBLIC_URL,
            }
            message = EmailMessage(
                subject=render_to_string(
                    "orders/emails/low_stock_report_subject.txt", context
                ).strip(),
                body=render_to_string("orders/emails/low_stock_report.txt", context),
                from_email=settings.DEFAULT_FROM_EMAIL,
                # bcc: the managers don't see each other's addresses
                bcc=emails,
            )
        for name, content in attachments:
            message.attach(name, content, "text/csv")
        message.send()

    count = sum(len(emails) for emails in by_language.values())
    logger.info(
        "Low stock report %s sent to %s managers: %s books", report.day, count, len(report.books)
    )
    return count
