"""Load the exchange rates of the active currencies from the NBU.

Usage:
    python manage.py update_exchange_rates                     # today + the newest day
    python manage.py update_exchange_rates --date 2026-11-14   # one past day

Runs on its own every day (Celery Beat: currencies.tasks.update_exchange_rates);
by hand it does the same, e.g. right after the first deploy, to have rates
at once. A manual rate entered in the admin for the same day is kept.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext as _
from requests import RequestException

from currencies.nbu import NBUError
from currencies.services import update_current_rates, update_rates


class Command(BaseCommand):
    help = "Load the exchange rates of the active currencies from the NBU."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            # argparse calls it with the text: "2026-11-14" -> date(2026, 11, 14)
            type=date.fromisoformat,
            help="the day of the rates, YYYY-MM-DD (default: today and the newest day)",
        )

    def handle(self, *args, **options):
        try:
            if options["date"]:
                results = [update_rates(options["date"])]
            else:
                results = update_current_rates()
        except (RequestException, NBUError) as error:
            raise CommandError(_("Can't load the NBU rates: %(error)s") % {"error": error})
        for result in results:
            self.show(result)

    def show(self, result):
        day = f"{result.date:%d.%m.%Y}"
        for code, value in result.saved.items():
            self.stdout.write(
                _("%(code)s on %(date)s: %(rate)s UAH") % {"code": code, "date": day, "rate": value}
            )
        for code in result.kept_manual:
            self.stdout.write(
                _("%(code)s on %(date)s: the manual rate is kept") % {"code": code, "date": day}
            )
        for code in result.missing:
            self.stdout.write(
                self.style.WARNING(
                    _("%(code)s: the NBU has no rate on %(date)s") % {"code": code, "date": day}
                )
            )
        self.stdout.write(self.style.SUCCESS(_("Saved: %(count)s.") % {"count": len(result.saved)}))
