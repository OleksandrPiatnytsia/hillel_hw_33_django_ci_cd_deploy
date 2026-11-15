"""Currencies and their exchange rates to the hryvnia.

Currency       one row per currency: UAH, USD, EUR (data migration 0002)
ExchangeRate   the history of rates: one row per currency per day

The base currency is UAH: the National Bank of Ukraine (NBU) publishes
every rate as "how many hryvnias for 1 unit", so a rate is stored the same
way and UAH itself has no rate rows (its rate is always 1). A rate between
two other currencies (USD -> EUR) is calculated through UAH and never
stored: rate(USD) / rate(EUR). See currencies/services.py.
"""

from decimal import Decimal

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

# The currency of every rate: rates are "UAH for 1 unit"
BASE_CURRENCY = "UAH"


class Currency(models.Model):
    # ISO 4217 code as the primary key: "USD" is short, never changes and is
    # what the NBU API, Stripe ("usd") and the URLs (?currency=USD) use.
    # A foreign key to a currency stores "USD" itself, not a number.
    code = models.CharField(
        _("code"),
        max_length=3,
        primary_key=True,
        validators=[RegexValidator(r"^[A-Z]{3}$", _("Three capital Latin letters (ISO 4217)."))],
        help_text=_("ISO 4217, for example USD"),
    )
    name = models.CharField(_("name"), max_length=50)
    symbol = models.CharField(_("symbol"), max_length=5)
    # Off: the currency is not offered on the site any more, its rates are
    # not updated. Not deleted: books and orders keep a link to it (PROTECT).
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = _("currency")
        verbose_name_plural = _("currencies")

    def __str__(self):
        return self.code

    @property
    def is_base(self):
        return self.code == BASE_CURRENCY


class ExchangeRate(models.Model):
    """The rate of one currency on one day: how many UAH for 1 unit.

    The whole history stays in the table (2 currencies * 365 days ~ 730 rows
    a year): the rate of a past day can always be shown, and on a weekend
    or when the NBU is down the last known rate is used.
    """

    class Source(models.TextChoices):
        # Loaded from the NBU API (update_exchange_rates, Celery Beat)
        NBU = "nbu", _("NBU")
        # Entered by hand in the admin; the NBU update never overwrites it
        MANUAL = "manual", _("Manual")

    currency = models.ForeignKey(
        Currency,
        verbose_name=_("currency"),
        # PROTECT: a currency with a rate history can't be deleted
        # (turn it off with is_active instead)
        on_delete=models.PROTECT,
        related_name="rates",  # currency.rates.all()
    )
    # The day the rate is set for. The NBU publishes the rate of the next
    # day in the afternoon, so the newest row is often "tomorrow"; the
    # current rate is the newest one with date <= today (services.today()).
    date = models.DateField(_("date"))
    # 6 decimal places, like the NBU (0.332040 UAH for 1 Algerian dinar);
    # up to 999 999.999999 UAH for 1 unit
    rate = models.DecimalField(
        _("rate"),
        max_digits=12,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
        help_text=_("How many hryvnias for 1 unit of the currency"),
    )
    source = models.CharField(
        _("source"),
        max_length=10,
        choices=Source,
        default=Source.MANUAL,
    )
    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        ordering = ["-date", "currency"]
        verbose_name = _("exchange rate")
        verbose_name_plural = _("exchange rates")
        constraints = [
            # One rate per currency per day. The unique index on
            # (currency, date) also serves "the newest rate of USD up to today".
            models.UniqueConstraint(
                fields=["currency", "date"], name="currencies_rate_one_per_day"
            ),
            models.CheckConstraint(condition=models.Q(rate__gt=0), name="currencies_rate_positive"),
            # UAH is the base: its rate is always 1 and never stored
            models.CheckConstraint(
                condition=~models.Q(currency=BASE_CURRENCY),
                name="currencies_rate_not_for_base_currency",
            ),
        ]

    def __str__(self):
        return f"{self.currency_id} {self.date:%d.%m.%Y}: {self.rate} {BASE_CURRENCY}"
