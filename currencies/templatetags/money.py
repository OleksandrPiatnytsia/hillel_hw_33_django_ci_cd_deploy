"""Prices in templates: {% load money %}.

{% book_price book as price %}      the price in the switcher's currency
{{ price }}                          "14,31 $"
{% if price.converted %}{{ price.original }} ...{% endif %}

{{ cart.total|money:cart.currency }} an amount that already has its
                                     currency (no conversion): "650,00 ₴"
"""

from django import template

from ..display import book_price as _book_price
from ..display import format_money

register = template.Library()


@register.simple_tag(takes_context=True)
def book_price(context, book):
    return _book_price(context["request"], book)


@register.filter
def money(amount, currency):
    """{{ 650|money:"UAH" }} -> "650,00 ₴"; currency: a Currency or a code."""
    if amount is None or amount == "":
        return ""
    return format_money(amount, currency)
