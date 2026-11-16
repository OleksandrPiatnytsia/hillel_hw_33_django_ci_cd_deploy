"""Small helpers for the tests (not fixtures: plain functions).

Texts of the messages are NOT compared in the tests: after the i18n stage
they are shown in Ukrainian or English. The tests check what happened
(database, status code, redirect, message level), the i18n tests check
the texts in both languages separately.
"""

from django.contrib.messages import get_messages
from django.db.models import Model


def message_levels(response):
    """["success"], ["error", "error"], ...: levels of the flash messages."""
    return [message.level_tag for message in get_messages(response.wsgi_request)]


def admin_change_form_data(response):
    """POST data of an admin change page, as the browser would send it unchanged.

    Takes the GET response of /admin/<app>/<model>/<pk>/change/ and copies
    every value: the main form, and for every inline its management form
    (TOTAL_FORMS, INITIAL_FORMS, ...) and the rows it already has.
    A test then changes only what it needs:

        data = admin_change_form_data(client.get(url))
        data["status"] = "cancelled"
        client.post(url, data)

    Without this a test would have to know the prefix of every inline
    ("items-", "payments-", "payments-2-") and repeat them by hand.
    """

    def as_post_value(value):
        if isinstance(value, Model):
            return value.pk
        return "" if value is None else value

    data = {}
    form = response.context["adminform"].form
    for name, field in form.fields.items():
        data[name] = as_post_value(form.initial.get(name, field.initial))

    for inline in response.context["inline_admin_formsets"]:
        formset = inline.formset
        management = formset.management_form
        for name in management.fields:
            data[management.add_prefix(name)] = management.initial.get(name, "")
        for row in formset.forms:
            for name, field in row.fields.items():
                data[row.add_prefix(name)] = as_post_value(row.initial.get(name, field.initial))
    return data


def inline_prefix(response, formset_class):
    """Prefix of the inline whose formset is formset_class ("payments-2")."""
    for inline in response.context["inline_admin_formsets"]:
        if isinstance(inline.formset, formset_class):
            return inline.formset.prefix
    raise LookupError(f"No inline with {formset_class.__name__} on the page")


def format_row(format_type="paper", price="250.00", currency="UAH", **fields):
    """One row of the formats block of the book form: {"format_type": ..., ...}.

    is_active is "on" (the checkbox is ticked by default); pass
    is_active="" to send it unticked, id=<pk> for a saved format.
    """
    return {
        "format_type": format_type,
        "price": price,
        "currency": currency,
        "is_active": "on",
        **fields,
    }


def formats_data(*rows, initial=0):
    """POST data of the formats block of the book form (BookFormatFormSet).

    rows: format_row(...) dicts; initial: how many of them are saved
    formats (they come first and carry their "id"). Without the
    management form (TOTAL_FORMS, INITIAL_FORMS) Django refuses the
    whole formset.
    """
    data = {
        "formats-TOTAL_FORMS": len(rows),
        "formats-INITIAL_FORMS": initial,
        "formats-MIN_NUM_FORMS": 0,
        "formats-MAX_NUM_FORMS": 1000,
    }
    for index, row in enumerate(rows):
        for name, value in row.items():
            data[f"formats-{index}-{name}"] = value
    return data
