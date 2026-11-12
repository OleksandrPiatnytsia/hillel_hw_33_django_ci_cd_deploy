from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import User
from .phone import normalize_phone


class BootstrapFormMixin:
    """Adds Bootstrap's "form-control" class to every field widget.

    The auth forms come from Django, so we can't list widgets in Meta like
    in BookForm — instead the classes are added after the fields are built.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    """Login by username + password (Django's AuthenticationForm)."""


class SignUpForm(BootstrapFormMixin, UserCreationForm):
    """Registration: username, email, password + confirmation.

    UserCreationForm already does the important parts: checks that the two
    passwords match, runs AUTH_PASSWORD_VALIDATORS, rejects a username that
    differs only by case, and saves the password as a hash (set_password).

    No clean_email() needed: User.clean() lowercases the email before the
    unique check, so "Ann@Mail.com" is caught as a duplicate of "ann@mail.com"
    (error text comes from error_messages on the model field).
    """

    class Meta(UserCreationForm.Meta):
        # The parent Meta points to the built-in auth.User; our model
        # replaced it (AUTH_USER_MODEL), so the form must use users.User
        model = User
        fields = ("username", "email")


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    """The user's own data for the checkout: name, phone, delivery address.

    Not username / email / password: those have their own rules (unique,
    confirmation) and are not part of this homework.
    """

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "address"]
        widgets = {
            "phone": forms.TextInput(
                attrs={"type": "tel", "autocomplete": "tel", "placeholder": "+380 67 123 45 67"}
            ),
            "address": forms.Textarea(
                attrs={
                    "rows": 3,
                    "autocomplete": "street-address",
                    "placeholder": _("City, street, house, flat or the post office number"),
                }
            ),
        }

    def clean_phone(self):
        # The same check as at checkout: a saved phone always passes there
        return normalize_phone(self.cleaned_data["phone"])
