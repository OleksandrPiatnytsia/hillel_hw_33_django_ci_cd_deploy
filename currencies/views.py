import logging
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core import signing
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext
from django.views import View
from django.views.decorators.http import require_POST

from . import nbu
from .display import SESSION_KEY
from .forms import ConfirmRatesForm, read_snapshot, sign_snapshot
from .models import BASE_CURRENCY, Currency, ExchangeRate
from .services import available_currencies, save_confirmed_rates

logger = logging.getLogger(__name__)


@require_POST
def set_currency(request):
    """The currency switcher in the navbar: POST currency=USD, next=<page>.

    POST, like the language switcher: it changes the visitor's state (the
    session), a plain link could be followed by a bot or another site.
    Only a currency offered on the site is saved; anything else (an old
    page with a currency turned off since, a crafted form) changes nothing.
    Then back to `next` (only an address of this site: no open redirect).
    """
    code = request.POST.get("currency", "")
    if code in {currency.code for currency in available_currencies()}:
        request.session[SESSION_KEY] = code

    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("books:list")


class NBURatesView(PermissionRequiredMixin, View):
    """/currencies/rates/: load the NBU rates, check them, save with a button.

    GET   asks the NBU (the newest rates, or ?date=2026-11-16) and shows a
          table: the NBU number, the rate saved for that day (with its
          source) and a field with the NBU number in it. Nothing is saved.
    POST  saves the confirmed fields (services.save_confirmed_rates): an
          unchanged field is "nbu", a changed one "manual" (the automatic
          update keeps a manual rate). Then back to GET (Post/Redirect/Get).

    For the people who may add and change rates in the admin (a superuser,
    or a group with both permissions): the same right, a handier page.
    Anonymous -> the login page; logged in without the right -> 403.
    """

    permission_required = ["currencies.add_exchangerate", "currencies.change_exchangerate"]
    template_name = "currencies/rates.html"

    def currencies(self):
        # The automatic update loads only active currencies: the same here
        return Currency.objects.filter(is_active=True).exclude(code=BASE_CURRENCY)

    def get(self, request):
        day, day_error = self.requested_day()
        # Every key the template reads, also when there is no table
        context = {"day": day, "day_error": day_error, "rate_date": None, "form": None}
        if day_error:
            return render(request, self.template_name, context)
        try:
            answer = nbu.fetch_rates(day)
        except (nbu.NBUError, OSError) as error:
            # OSError: no connection, timeout, HTTP 5xx (requests' errors)
            logger.warning("NBU rates page: the NBU did not answer: %r", error)
            context["nbu_error"] = gettext("The NBU did not answer. Try again in a minute.")
            return render(request, self.template_name, context)
        if not answer:
            # A day in the future: the NBU answers with an empty list
            context["nbu_error"] = gettext("The NBU has no rates for this day yet.")
            return render(request, self.template_name, context)

        # The day comes from the NBU (without ?date= the NBU picks the newest)
        rate_date = next(iter(answer.values())).date
        currencies = self.currencies()
        published = {c.code: answer[c.code].rate for c in currencies if c.code in answer}
        form = ConfirmRatesForm(
            currencies=currencies,
            published=published,
            initial={"snapshot": sign_snapshot(rate_date, published)},
        )
        return render(request, self.template_name, self.table_context(context, form, rate_date))

    def post(self, request):
        try:
            date_text, published = read_snapshot(request.POST.get("snapshot", ""))
        except signing.BadSignature:  # forged, or older than SNAPSHOT_MAX_AGE
            messages.error(request, gettext("The page is out of date: the rates are loaded again."))
            return redirect("currencies:rates")
        rate_date = date.fromisoformat(date_text)
        form = ConfirmRatesForm(request.POST, currencies=self.currencies(), published=published)
        if not form.is_valid():
            context = self.table_context({"day": rate_date}, form, rate_date)
            return render(request, self.template_name, context)

        sources = save_confirmed_rates(rate_date, form.rates(), published, user=request.user)
        if sources:
            labels = dict(ExchangeRate.Source.choices)
            saved = ", ".join(f"{code} ({labels[source]})" for code, source in sources.items())
            messages.success(
                request,
                gettext("Rates for %(date)s saved: %(saved)s.")
                % {"date": f"{rate_date:%d.%m.%Y}", "saved": saved},
            )
        else:
            messages.info(request, gettext("Nothing to save: every field is empty."))
        return redirect(f"{reverse('currencies:rates')}?date={rate_date.isoformat()}")

    def requested_day(self):
        """(date or None, error text or None) from ?date=YYYY-MM-DD."""
        value = self.request.GET.get("date")
        if not value:
            return None, None
        try:
            return date.fromisoformat(value), None
        except ValueError:
            return None, gettext("Wrong date: %(value)s.") % {"value": value}

    def table_context(self, context, form, rate_date):
        saved = {
            rate.currency_id: rate
            for rate in ExchangeRate.objects.filter(date=rate_date, currency__in=form.currencies)
        }
        return {**context, "form": form, "rate_date": rate_date, "rows": form.rows(saved)}
