from django.utils.functional import SimpleLazyObject

from .display import display_currency
from .services import available_currencies


def currency(request):
    """The switcher's data in every template rendered with a request.

    display_currency    the Currency prices are shown in (navbar button)
    currency_choices    the currencies of the switcher's menu

    Lazy: read only when a template uses them (the navbar does on every
    page; a JSON or a redirect doesn't render a template at all).
    """
    return {
        "display_currency": SimpleLazyObject(lambda: display_currency(request)),
        "currency_choices": SimpleLazyObject(available_currencies),
    }
