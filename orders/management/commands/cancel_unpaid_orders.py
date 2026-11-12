"""Cancel old unpaid orders and return their books to the stock.

An order reserves its books at checkout. If the customer never pays, the
books stay out of the stock forever; this command gives them back.

Usage:
    python manage.py cancel_unpaid_orders                    # older than 24 hours
    python manage.py cancel_unpaid_orders --older-than 30m   # 30m, 12h, 2d
    python manage.py cancel_unpaid_orders --dry-run          # only show them

Runs every hour on its own (Celery Beat: orders.tasks.cancel_unpaid_orders);
by hand it does the same. The customer of every cancelled order gets the
email "order cancelled" (not with --dry-run).
"""

import argparse
import logging
import re
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from orders.models import Order
from orders.services import OrderError, cancel_order

logger = logging.getLogger(__name__)  # "orders.management.commands.cancel_unpaid_orders"

UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def parse_age(value):
    """ "30m" / "24h" / "2d" -> timedelta; argparse calls it for --older-than."""
    match = re.fullmatch(r"(\d+)([mhd])", value.strip().lower())
    if not match or int(match[1]) == 0:
        # ArgumentTypeError: argparse shows this text as the error message
        raise argparse.ArgumentTypeError(
            f"{value!r} is not an age: use a number + m / h / d, e.g. 30m, 24h, 2d"
        )
    return timedelta(**{UNITS[match[2]]: int(match[1])})


class Command(BaseCommand):
    help = "Cancel new unpaid orders older than --older-than and return their books to stock."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than",
            type=parse_age,
            default=timedelta(hours=24),
            help="age of the order: a number + m / h / d (default: 24h)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="list the orders, change nothing",
        )

    def handle(self, *args, **options):
        age = options["older_than"]
        if age < timedelta(minutes=30):
            # A Stripe payment page lives 31 minutes: a younger order may be
            # being paid right now
            raise CommandError(_("--older-than must be at least 30m."))
        border = timezone.now() - age

        orders = Order.objects.filter(
            status=Order.Status.NEW,
            payment_status=Order.PaymentStatus.UNPAID,
            created_at__lt=border,
        ).order_by("created_at")

        if options["dry_run"]:
            for order in orders:
                # Not an f-string: it would put the values in BEFORE _(), so
                # gettext would look for "would cancel Order #5 from ..." in
                # the .po file and never find it (and makemessages skips
                # f-strings). The template with %(name)s is translated first,
                # the values are put in after (% {...}).
                self.stdout.write(
                    _("would cancel %(order)s from %(date)s (%(total)s UAH)")
                    % {
                        "order": order,
                        "date": f"{order.created_at:%d.%m.%Y %H:%M}",
                        "total": order.total,
                    }
                )
            count = orders.count()
            self.stdout.write(
                ngettext(
                    "%(count)s order, nothing changed (--dry-run).",
                    "%(count)s orders, nothing changed (--dry-run).",
                    count,
                )
                % {"count": count}
            )
            return

        cancelled = skipped = 0
        # values_list: only the ids; each order is read again under its lock
        # in cancel_order(), with only_unpaid=True — a payment that arrived
        # after this SELECT wins, the order is skipped
        for order_id in orders.values_list("pk", flat=True):
            try:
                cancel_order(order_id, only_unpaid=True, notify_customer=True)
            except OrderError as error:
                skipped += 1
                self.stdout.write(self.style.WARNING(_("skipped: %(error)s") % {"error": error}))
                continue
            cancelled += 1
            self.stdout.write(_("cancelled: order #%(number)s") % {"number": order_id})
            logger.info("Order #%s cancelled: unpaid for more than %s", order_id, age)

        # Every run, also with nothing to do: the log shows that the hourly
        # run (Celery Beat) happened, not only the runs that cancelled something
        logger.info(
            "Unpaid orders older than %s: cancelled %s, skipped %s", age, cancelled, skipped
        )
        self.stdout.write(
            # "Cancelled: 3" instead of "Cancelled 3 order(s)": no plural forms needed
            self.style.SUCCESS(
                _("Cancelled: %(cancelled)s, skipped: %(skipped)s.")
                % {"cancelled": cancelled, "skipped": skipped}
            )
        )
