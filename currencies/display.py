"""Prices on the site: the currency of the switcher and the money format.

    display_currency(request)    Currency the visitor chose (session), UAH by default
    book_price(request, book)    the price of a book in that currency + the original
    format_money(14.31, "USD")   "14,31 $" (uk) / "$14.31" (en)

The choice lives in the session (key "currency"), like the cart: a guest
has it too, and it stays after logging in. The navbar switcher sends it to
currencies.views.set_currency.

Everything here is read many times per page (24 prices in the catalog), so
the rates and the chosen currency are kept on the request object: one
cache read per request, not one per price.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils.formats import number_format
from django.utils.translation import get_language

from .models import BASE_CURRENCY, Currency
from .services import all_currencies, available_currencies, convert, current_rates

SESSION_KEY = "currency"


def request_rates(request):
    """current_rates(), read once per request."""
    if not hasattr(request, "_currency_rates"):
        request._currency_rates = current_rates()
    return request._currency_rates


def display_currency(request):
    """The Currency prices are shown in: the switcher's choice, or UAH.

    A code in the session that is not offered any more (turned off in the
    admin, no rate) falls back to UAH instead of failing.
    """
    if not hasattr(request, "_display_currency"):
        offered = {currency.code: currency for currency in available_currencies()}
        code = request.session.get(SESSION_KEY)
        currency = offered.get(code) or all_currencies().get(BASE_CURRENCY)
        if currency is None:  # pragma: no cover - the data migration creates UAH
            currency = Currency.objects.get(code=BASE_CURRENCY)
        request._display_currency = currency
    return request._display_currency


def format_money(amount, currency):
    """650.00 + UAH -> "650,00 ₴"; 14.31 + USD -> "14,31 $" / "$14.31".

    currency: a Currency or its code. The number in the format of the
    current language (a decimal comma in Ukrainian). The symbol goes after
    the number, as Ukrainians write it; in English $ and € go before it
    ("$14.31"), the hryvnia stays after it ("650.00 ₴").
    """
    if not isinstance(currency, Currency):
        currency = all_currencies().get(currency) or Currency(code=currency, symbol=currency)
    number = number_format(amount, 2)
    if get_language() == "en" and not currency.is_base:
        return f"{currency.symbol}{number}"
    return f"{number} {currency.symbol}"


@dataclass(frozen=True)
class BookPrice:
    amount: Decimal  # in `currency`
    currency: Currency  # the currency of the switcher
    original_amount: Decimal  # Book.price
    original_currency: Currency  # Book.currency
    # The day of the exchange rate used (None: no conversion)
    rate_date: date | None

    @property
    def converted(self):
        return self.original_currency.code != self.currency.code

    def __str__(self):
        return format_money(self.amount, self.currency)

    @property
    def original(self):
        return format_money(self.original_amount, self.original_currency)


def book_price(request, book):
    """The price of a book in the currency of the switcher.

    A book in a currency that has no rate (only if its rates were deleted
    by hand) keeps its own currency: better a price in EUR than an error.
    """
    currencies = all_currencies()
    original_currency = currencies[book.currency_id]
    target = display_currency(request)
    rates = request_rates(request)
    if book.currency_id == target.code or book.currency_id not in rates:
        return BookPrice(book.price, original_currency, book.price, original_currency, None)
    # The rate date: of the non-UAH side; of both, the newer one
    rate_dates = [rates[code].date for code in (book.currency_id, target.code) if rates[code].date]
    return BookPrice(
        amount=convert(book.price, book.currency_id, target.code, rates),
        currency=target,
        original_amount=book.price,
        original_currency=original_currency,
        rate_date=max(rate_dates),
    )
