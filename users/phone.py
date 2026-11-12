import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


def normalize_phone(value):
    """ "+380 (67) 123-45-67" -> "+380671234567"; ValidationError if it's not a phone.

    Shared by the profile form and the checkout form, so a phone saved in
    the profile always passes the checkout check. Empty -> "".
    """
    value = value.strip()
    if not value:
        return ""
    digits = re.sub(r"\D", "", value)  # \D = any non-digit
    if not re.fullmatch(r"\+?[\d\s()\-]+", value) or not 10 <= len(digits) <= 15:
        raise ValidationError(_("Enter a phone number: 10–15 digits, e.g. +380 67 123 45 67."))
    return ("+" if value.startswith("+") else "") + digits
