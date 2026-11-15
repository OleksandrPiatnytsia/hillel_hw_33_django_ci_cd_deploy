"""GET /api/currencies/[<code>/]: the currencies offered, with today's rate.

The same list as the switcher of the site: active currencies that have a
rate today, UAH first. Read only and open to everybody; the currencies and
rates are edited in the admin and loaded from the NBU (currencies app).
No pagination: a few currencies, all of them in one answer.
"""

from django.http import Http404
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from currencies.services import available_currencies, current_rates

from ..docs import currency_schema
from ..serializers.currencies import CurrencySerializer


@currency_schema
class CurrencyViewSet(viewsets.ViewSet):
    """list and retrieve, from the cached rates (no SQL on a warm cache)."""

    permission_classes = [AllowAny]
    serializer_class = CurrencySerializer  # for /api/docs/
    lookup_value_regex = "[A-Za-z]{3}"  # /api/currencies/usd/ works too

    def _serializer(self, data, **kwargs):
        return CurrencySerializer(data, context={"rates": current_rates()}, **kwargs)

    def list(self, request):
        return Response(self._serializer(available_currencies(), many=True).data)

    def retrieve(self, request, pk=None):
        code = pk.upper()
        for currency in available_currencies():
            if currency.code == code:
                return Response(self._serializer(currency).data)
        raise Http404
