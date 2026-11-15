"""Filters of the catalog API (django-filter) and a stable ordering.

A FilterSet turns GET parameters into .filter() calls:
    /api/books/?category=fantasy&price_min=100&stock=in_stock
Unknown parameters are ignored; a wrong value (?price_min=abc,
?category=no-such-slug) -> 400 with the error of the parameter.
"""

import django_filters
from django import forms
from django.db.models import F
from django.utils.translation import gettext_lazy as _
from rest_framework.filters import OrderingFilter

from books.models import Author, Book, BookQuerySet, Category


class BookFilterForm(forms.Form):
    """The form behind BookFilter: the check of the price range.

    django-filter builds a form from the filters to validate the
    parameters; Meta.form gives it this base class with our clean().
    """

    def clean(self):
        cleaned_data = super().clean()
        price_min = cleaned_data.get("price_min")
        price_max = cleaned_data.get("price_max")
        # The site ignores such a range and shows a hint; an API client
        # gets 400: "from 500 to 100" is a mistake in its code
        # The error goes to price_min: django-filter answers with form.errors,
        # where an error of the whole form would be under the key "__all__"
        if price_min is not None and price_max is not None and price_min > price_max:
            self.add_error("price_min", _("“Price from” can't be greater than “Price to”."))
        return cleaned_data


class BookFilter(django_filters.FilterSet):
    """The same filters as the catalog page of the site (books.forms.BookFilterForm).

    ?category=<slug>      books of a category (slug, like on the site)
    ?author=<id>          books of an author
    ?price_min= / ?price_max=   price range, both ends included, in the
                          currency of ?currency= (display_price, UAH by
                          default): books of every currency are compared
    ?stock=in_stock | low | out  availability (BookQuerySet.by_stock_status)
    The text search (?search=) and the sort (?ordering=) come from
    SearchFilter / OrderingFilter in the ViewSet.
    """

    category = django_filters.ModelChoiceFilter(
        field_name="categories",
        queryset=Category.objects.all(),
        to_field_name="slug",
    )
    author = django_filters.ModelChoiceFilter(queryset=Author.objects.all())
    # display_price: the annotation of BookViewSet (the converted price)
    price_min = django_filters.NumberFilter(
        field_name="display_price", lookup_expr="gte", min_value=0
    )
    price_max = django_filters.NumberFilter(
        field_name="display_price", lookup_expr="lte", min_value=0
    )
    stock = django_filters.ChoiceFilter(
        choices=BookQuerySet.STOCK_STATUS_CHOICES,
        method="filter_stock",
    )

    class Meta:
        model = Book
        fields = ["category", "author", "price_min", "price_max", "stock"]
        form = BookFilterForm

    def filter_stock(self, queryset, name, value):
        # method=: our own filtering instead of field_name + lookup_expr;
        # the rule "low = 1..5" lives in one place, the model's queryset
        return queryset.by_stock_status(value)


class StableOrderingFilter(OrderingFilter):
    """OrderingFilter (?ordering=price, ?ordering=-created_at) + "pk" at the end.

    Books with the same price (or title) would come back in any order the
    database likes, different from one query to the next: on page 2 a
    book from page 1 again, another one never. "pk" as the last column
    makes the order unique, like order_by(..., "pk") on the site.

    view.ordering_aliases: a name the client sends -> the field the
    database sorts by. BookViewSet: {"price": "display_price"}, so
    ?ordering=price sorts by the price in ONE currency, not by the numbers
    of different currencies. The books without a rate (NULL) go last in
    both directions, like on the site.
    """

    def filter_queryset(self, request, queryset, view):
        ordering = self.get_ordering(request, queryset, view)
        if not ordering:
            return queryset
        aliases = getattr(view, "ordering_aliases", {})
        return queryset.order_by(*(self._expression(field, aliases) for field in ordering))

    @staticmethod
    def _expression(field, aliases):
        name = field.removeprefix("-")
        if name not in aliases:
            return field
        column = F(aliases[name])
        if field.startswith("-"):
            return column.desc(nulls_last=True)
        return column.asc(nulls_last=True)

    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        # None: no ?ordering= (or only unknown fields) -> the queryset keeps
        # the order_by() of the ViewSet, which ends with "pk" already.
        # A client can't send "pk" itself: it is not in ordering_fields.
        if not ordering:
            return ordering
        return [*ordering, "pk"]
