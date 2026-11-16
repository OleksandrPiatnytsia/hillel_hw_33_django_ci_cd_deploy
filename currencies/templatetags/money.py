"""Prices in templates: {% load money %}.

{% book_price book_format as price %} the price of a format in the switcher's currency
{% price_from book as price %}      the cheapest format on sale, None if none
{{ price }}                          "14,31 $"
{% if price.converted %}{{ price.original }} ...{% endif %}

{{ cart.total|money:cart.currency }} an amount that already has its
                                     currency (no conversion): "650,00 ₴"
"""

from django import template

from ..display import book_price as _book_price
from ..display import format_money
from ..display import price_from as _price_from

register = template.Library()


@register.simple_tag(takes_context=True)
def book_price(context, book_format):
    return _book_price(context["request"], book_format)


@register.simple_tag(takes_context=True)
def price_from(context, book):
    return _price_from(context["request"], book)


@register.filter
def money(amount, currency):
    """{{ 650|money:"UAH" }} -> "650,00 ₴"; currency: a Currency or a code."""
    if amount is None or amount == "":
        return ""
    return format_money(amount, currency)
