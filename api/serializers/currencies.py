"""The currencies of the shop with today's NBU rate: GET /api/currencies/.

    [{"code": "UAH", "name": "Ukrainian hryvnia", "symbol": "₴",
      "rate": "1.000000", "rate_date": null},
     {"code": "USD", "name": "US dollar", "symbol": "$",
      "rate": "45.427400", "rate_date": "2026-11-16"}]

rate: how many UAH for 1 unit; rate_date: the day of that NBU rate (null
for UAH, the base currency). A client converts a price itself with them,
or asks /api/books/?currency=USD and gets display_price ready.
"""

from decimal import Decimal

from rest_framework import serializers


class CurrencySerializer(serializers.Serializer):
    """One currency + its rate (currencies.services.Rate in the context)."""

    code = serializers.CharField()
    name = serializers.CharField()
    symbol = serializers.CharField()
    rate = serializers.SerializerMethodField()
    rate_date = serializers.SerializerMethodField()

    def _rate(self, currency):
        return self.context["rates"][currency.code]

    def get_rate(self, currency) -> Decimal:
        return f"{self._rate(currency).value:.6f}"

    def get_rate_date(self, currency) -> str | None:
        day = self._rate(currency).date
        return day.isoformat() if day else None
