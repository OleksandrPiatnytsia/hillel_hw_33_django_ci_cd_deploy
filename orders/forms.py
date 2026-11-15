from django import forms

from django.utils.translation import gettext_lazy as _

from currencies.services import available_currencies
from users.phone import normalize_phone

from .models import Order


def currency_choices():
    """Only the currencies offered now (active, with a rate)."""
    return [(currency.code, currency.code) for currency in available_currencies()]


class CheckoutForm(forms.ModelForm):
    """Delivery data on the checkout page.

    Only the three fields the user fills in. user, total and the statuses
    are set by orders.services.create_order(), never taken from the form —
    otherwise a crafted POST could send total=1.
    The email is not asked: it's taken from the user's profile.
    """

    # Not an Order field: after the order is created, the view copies phone
    # and address to the user's profile for the next checkout
    save_to_profile = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Save phone and address to my profile"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    # The order currency: the one the page showed the cart in (the switcher),
    # sent back in a hidden field. Not taken from the session at POST time:
    # the switcher changed in another tab would make an order in a currency
    # the customer didn't see on this page. Not in Meta.fields: the view
    # passes it to create_order(), like the delivery data. Not required: a
    # POST without it (an old page, a script) gets the currency of the cart.
    # Choices: a function, read only when the field is checked or shown, so
    # the currencies are not read from the database for an empty value.
    currency = forms.ChoiceField(required=False, choices=currency_choices, widget=forms.HiddenInput)

    class Meta:
        model = Order
        fields = ["full_name", "phone", "address"]
        # Labels come from the model fields (verbose_name, translated there)
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "name"}),
            # type="tel": a phone keyboard on mobile
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "type": "tel",
                    "autocomplete": "tel",
                    "placeholder": "+380 67 123 45 67",
                }
            ),
            "address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "autocomplete": "street-address",
                    "placeholder": _("City, street, house, flat or the post office number"),
                }
            ),
        }

    def clean_full_name(self):
        return " ".join(self.cleaned_data["full_name"].split())  # extra spaces out

    def clean_phone(self):
        """Allow "+380 (67) 123-45-67" and similar; store "+380671234567"."""
        return normalize_phone(self.cleaned_data["phone"])
