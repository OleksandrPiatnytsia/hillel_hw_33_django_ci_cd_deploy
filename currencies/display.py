"""Prices on the site: the currency of the switcher and the money format.

    display_currency(request)    Currency the visitor chose (session), UAH by default
    book_price(request, format)  the price of a format of a book in that currency + the original
    price_from(request, book)    the cheapest format on sale of a book (None: nothing on sale)
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
    original_amount: Decimal  # the price of the format
    original_currency: Currency  # its currency
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


def book_price(request, book_format):
    """The price of one format of a book in the currency of the switcher.

    book_format: anything with .price and .currency_id (a BookFormat; the
    book itself has no price, its formats have). A format in a currency
    that has no rate (only if its rates were deleted by hand) keeps its
    own currency: better a price in EUR than an error.
    """
    currencies = all_currencies()
    code = book_format.currency_id
    original_currency = currencies[code]
    target = display_currency(request)
    rates = request_rates(request)
    if code == target.code or code not in rates:
        return BookPrice(
            book_format.price, original_currency, book_format.price, original_currency, None
        )
    # The rate date: of the non-UAH side; of both, the newer one
    rate_dates = [rates[c].date for c in (code, target.code) if rates[c].date]
    return BookPrice(
        amount=convert(book_format.price, code, target.code, rates),
        currency=target,
        original_amount=book_format.price,
        original_currency=original_currency,
        rate_date=max(rate_dates),
    )


def price_from(request, book):
    """The price "from" of a book: its cheapest format on sale, or None.

    The same choice as Book.objects.with_display_price() makes in SQL: the
    lowest price in the currency of the switcher. A format in a currency
    without a rate (it keeps its own currency, see book_price) is only
    used when no other format is on sale.
    None: the book has no format on sale ("Not on sale").
    """
    target = display_currency(request).code
    prices = [book_price(request, book_format) for book_format in book.active_formats]
    if not prices:
        return None
    # False sorts before True: the prices in the switcher's currency first
    return min(prices, key=lambda price: (price.currency.code != target, price.amount))
