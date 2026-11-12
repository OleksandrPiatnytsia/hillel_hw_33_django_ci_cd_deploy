"""The daily sales report for the "Managers" group (Celery Beat, every morning).

    report = build_daily_report(date(2026, 11, 10))
    report.orders_count, report.revenue, report.top_books, report.low_stock
    report.csv_files()  -> [("orders_2026-11-10.csv", b"..."), ...]
    send_daily_report_email(report)

Three CSV attachments (open in Excel / Google Sheets):
    orders_<day>.csv      every order created that day, cancelled ones too
    top_books_<day>.csv   the best sellers of the day (not cancelled orders)
    low_stock_<day>.csv   books with 0..LOW_STOCK_THRESHOLD copies NOW

"That day" is a calendar day in TIME_ZONE (UTC), like every date of the site.
"""

import csv
import io
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models import Count, F, Max, Sum
from django.template.loader import render_to_string
from django.utils import timezone, translation

from books.models import LOW_STOCK_THRESHOLD, Book
from users.models import User

from .models import Order, OrderItem

logger = logging.getLogger(__name__)  # "orders.reports"

MANAGERS_GROUP = "Managers"
TOP_BOOKS_LIMIT = 10


@dataclass
class DailyReport:
    day: object  # datetime.date
    orders: list  # Order objects of the day, with .user
    orders_count: int  # not cancelled
    cancelled_count: int
    paid_count: int
    revenue: Decimal  # sum of the totals of not cancelled orders
    top_books: list  # dicts: book_id, title, copies, revenue
    low_stock: list  # Book objects with .stock (with_stock())

    def csv_files(self):
        """[(file name, bytes), ...] for EmailMessage.attach()."""
        day = self.day.isoformat()
        return [
            (
                f"orders_{day}.csv",
                _csv(
                    [
                        "number",
                        "created_at",
                        "customer",
                        "email",
                        "status",
                        "payment_status",
                        "total",
                    ],
                    [
                        [
                            order.pk,
                            timezone.localtime(order.created_at).strftime("%Y-%m-%d %H:%M"),
                            order.user.username,
                            order.user.email,
                            order.status,
                            order.payment_status,
                            order.total,
                        ]
                        for order in self.orders
                    ],
                ),
            ),
            (
                f"top_books_{day}.csv",
                _csv(
                    ["book_id", "title", "copies", "revenue"],
                    [[b["book_id"], b["title"], b["copies"], b["revenue"]] for b in self.top_books],
                ),
            ),
            (
                f"low_stock_{day}.csv",
                _csv(
                    ["book_id", "title", "author", "stock"],
                    [[b.pk, b.title, b.author.name, b.stock] for b in self.low_stock],
                ),
            ),
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


def build_daily_report(day):
    start, end = day_bounds(day)
    # created_at__lt=end, not __lte or __date: the half-open range
    # [00:00, next 00:00) catches 23:59:59.999 and uses the index on created_at
    orders = list(
        Order.objects.filter(created_at__gte=start, created_at__lt=end)
        .select_related("user")
        .order_by("created_at")
    )
    active = [order for order in orders if order.status != Order.Status.CANCELLED]

    # GROUP BY book: copies and money per book. The title is the copy
    # saved in the order line; Max() picks one if it was renamed that day.
    top_books = list(
        OrderItem.objects.filter(order__in=[order.pk for order in active])
        .values("book_id")
        .annotate(
            title=Max("title"),
            copies=Sum("quantity"),
            revenue=Sum(F("price") * F("quantity")),
            orders=Count("order", distinct=True),
        )
        .order_by("-copies", "title")[:TOP_BOOKS_LIMIT]
    )

    low_stock = list(
        Book.objects.with_stock()
        .select_related("author")
        .filter(stock__lte=LOW_STOCK_THRESHOLD)
        .order_by("stock", "title")
    )

    return DailyReport(
        day=day,
        orders=orders,
        orders_count=len(active),
        cancelled_count=len(orders) - len(active),
        paid_count=sum(order.payment_status == Order.PaymentStatus.PAID for order in active),
        revenue=sum((order.total for order in active), start=Decimal("0.00")),
        top_books=top_books,
        low_stock=low_stock,
    )


def send_daily_report_email(report):
    """One email per language of the managers, with the CSV files attached.

    Raises on an SMTP / network error: the Celery task retries it (a retry
    may send the email again to the languages already done: a duplicate
    report is better than none). Returns the number of recipients.
    """
    managers = User.objects.filter(groups__name=MANAGERS_GROUP, is_active=True).exclude(email="")
    by_language = {}
    for manager in managers:
        by_language.setdefault(manager.language, []).append(manager.email)
    if not by_language:
        logger.warning("Daily report %s: no active managers with an email", report.day)
        return 0

    attachments = report.csv_files()
    for language, emails in by_language.items():
        with translation.override(language):
            context = {"report": report, "site_url": settings.SITE_URL}
            message = EmailMessage(
                subject=render_to_string("orders/emails/daily_report_subject.txt", context).strip(),
                body=render_to_string("orders/emails/daily_report.txt", context),
                from_email=settings.DEFAULT_FROM_EMAIL,
                # bcc: the managers don't see each other's addresses
                bcc=emails,
            )
        for name, content in attachments:
            message.attach(name, content, "text/csv")
        message.send()

    count = sum(len(emails) for emails in by_language.values())
    logger.info(
        "Daily report %s sent to %s managers: %s orders, %s UAH",
        report.day,
        count,
        report.orders_count,
        report.revenue,
    )
    return count
