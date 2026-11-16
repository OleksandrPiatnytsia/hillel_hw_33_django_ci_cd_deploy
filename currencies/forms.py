"""The form of the "NBU rates" page (currencies.views.NBURatesView)."""

from decimal import Decimal

from django import forms
from django.core import signing
from django.utils.translation import gettext_lazy as _

# The NBU answer travels with the form, signed: the POST knows exactly what
# the person saw (no second request to the NBU, which may answer
# differently a minute later), and a changed number in the hidden field
# breaks the signature
SNAPSHOT_SALT = "currencies.rates.snapshot"
# A page left open longer than this is loaded again: the NBU may have
# published new rates meanwhile
SNAPSHOT_MAX_AGE = 60 * 60


def sign_snapshot(rate_date, published):
    """The hidden field: the day and the NBU rates, signed with SECRET_KEY."""
    return signing.dumps(
        {"date": rate_date.isoformat(), "rates": {code: str(v) for code, v in published.items()}},
        salt=SNAPSHOT_SALT,
    )


def read_snapshot(value):
    """(date string, {code: Decimal}); signing.BadSignature if forged or too old."""
    data = signing.loads(value, salt=SNAPSHOT_SALT, max_age=SNAPSHOT_MAX_AGE)
    return data["date"], {code: Decimal(value) for code, value in data["rates"].items()}


class ConfirmRatesForm(forms.Form):
    """One rate field per currency (rate_USD, rate_EUR, ...) + the snapshot.

    The fields start with the NBU numbers. Left as they are -> saved as
    "nbu"; changed -> "manual" (services.save_confirmed_rates). An empty
    field -> this currency is not saved.
    """

    snapshot = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, currencies, published, **kwargs):
        super().__init__(*args, **kwargs)
        self.currencies = list(currencies)
        for currency in self.currencies:
            nbu_value = published.get(currency.code)
            self.fields[f"rate_{currency.code}"] = forms.DecimalField(
                label=currency.code,
                required=False,
                max_digits=12,
                decimal_places=6,
                min_value=Decimal("0.000001"),
                initial=nbu_value,
                # step="any": 45.4274 is valid (the default step 1 is not);
                # data-nbu: the script marks a changed field as "manual"
                widget=forms.NumberInput(
                    attrs={
                        "class": "form-control form-control-sm",
                        "step": "any",
                        "data-nbu": "" if nbu_value is None else str(nbu_value),
                    }
                ),
                error_messages={"min_value": _("The rate must be greater than zero.")},
            )

    def rates(self):
        """{code: Decimal or None} from cleaned_data."""
        return {c.code: self.cleaned_data.get(f"rate_{c.code}") for c in self.currencies}

    def rows(self, saved):
        """For the table: (currency, bound field, NBU number, saved ExchangeRate or None)."""
        return [
            (
                currency,
                self[f"rate_{currency.code}"],
                self.fields[f"rate_{currency.code}"].initial,
                saved.get(currency.code),
            )
            for currency in self.currencies
        ]
