"""Filters of the book catalog (django-filter), one set for the site and the API.

BookFilter turns GET parameters into .filter() calls:
    ?category=fantasy&category=poetry&author=3&author=7&stock=in_stock&price_min=100

Several values of one parameter (?author=3&author=7) mean "OR": books of
the author 3 or of the author 7. Different parameters mean "AND": books of
these authors that are also in one of these categories.

Who uses it:
    the site   CatalogFilter below (+ the text search ?q=), books.views.BookListView
    the API    api.filters.BookFilter (its own form: a wrong value -> 400)

A new filter of the panel (publisher, language, ...) is one more line here,
the site and the API get it at once.
"""

import django_filters
from django import forms
from django.db.models import Exists, OuterRef, Q
from django.utils.translation import gettext_lazy as _

from .models import Author, Book, BookCategory, BookQuerySet, Category


class BookFilter(django_filters.FilterSet):
    """The filters of the catalog; price_min/max need the "display_price" annotation.

    display_price: the price converted to one currency by the database
    (currencies.services.price_in), annotated by the view before filtering,
    so books priced in UAH and in USD are compared correctly.
    """

    category = django_filters.ModelMultipleChoiceFilter(
        # field_name: the model field, for the API docs (drf-spectacular
        # finds the type of the values there); the filtering is our method
        field_name="categories",
        queryset=Category.objects.all(),
        to_field_name="slug",  # ?category=fantasy instead of ?category=3
        method="filter_category",
        label=_("Category"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    author = django_filters.ModelMultipleChoiceFilter(
        queryset=Author.objects.all(),  # ?author=<pk>
        method="filter_author",
        label=_("Author"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    # One choice of three, like before: "Low" is a part of "In stock", as
    # checkboxes they would overlap
    stock = django_filters.ChoiceFilter(
        choices=BookQuerySet.STOCK_STATUS_CHOICES,
        method="filter_stock",
        label=_("Availability"),
        empty_label=_("Any"),
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )
    price_min = django_filters.NumberFilter(
        field_name="display_price",
        lookup_expr="gte",
        min_value=0,
        label=_("Price from"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    price_max = django_filters.NumberFilter(
        field_name="display_price",
        lookup_expr="lte",
        min_value=0,
        label=_("Price to"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    class Meta:
        model = Book
        fields = ["category", "author", "stock", "price_min", "price_max"]

    # method=: our own filtering instead of field_name + lookup_expr.
    # "value" is what the form field gave: a queryset of the chosen
    # objects, empty when nothing is chosen.

    def filter_category(self, queryset, name, value):
        if not value:
            return queryset
        # EXISTS (a subquery), not a JOIN with categories__in: a book that is
        # in two of the chosen categories would come twice, and .distinct()
        # does not go well with the annotations and the ordering of the list
        in_chosen = BookCategory.objects.filter(book=OuterRef("pk"), category__in=value)
        return queryset.filter(Exists(in_chosen))

    def filter_author(self, queryset, name, value):
        # A book has one author (ForeignKey): IN (...) gives no duplicates
        return queryset.filter(author__in=value) if value else queryset

    def filter_stock(self, queryset, name, value):
        # The rule "low = 1..5" lives in one place, the model's queryset
        return queryset.by_stock_status(value)


class CatalogFilterForm(forms.Form):
    """The form of the site's catalog: a wrong price range is skipped.

    "From 500 to 100" would always give an empty list: both prices are
    taken out of cleaned_data (the catalog ignores them and applies the
    other filters) and the hint is shown above the filters. The API answers
    such a range with 400 instead (api.filters.BookFilterForm).
    """

    def clean(self):
        cleaned_data = super().clean()
        price_min = cleaned_data.get("price_min")
        price_max = cleaned_data.get("price_max")
        if price_min is not None and price_max is not None and price_min > price_max:
            del cleaned_data["price_min"], cleaned_data["price_max"]
            raise forms.ValidationError(_("“Price from” can't be greater than “Price to”."))
        return cleaned_data


class CatalogFilter(BookFilter):
    """The catalog page: the filters + the text search + the chips.

    The API has its own search (?search=) and ordering (?ordering=) from
    DRF; the sort of the site (?sort=) is read by the view, it is not a
    filter.
    """

    SORT_CHOICES = [
        ("title", _("Title A→Z")),
        ("-title", _("Title Z→A")),
        ("author__name", _("Author A→Z")),
        ("price", _("Price: low to high")),
        ("-price", _("Price: high to low")),
        ("-created_at", _("Newest first")),
        # Copies ordered, cancelled orders not counted (BookQuerySet.with_sold)
        ("-sold", _("Most popular")),
    ]

    q = django_filters.CharFilter(
        method="search",
        label=_("Search"),
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Title or author")}
        ),
    )

    class Meta(BookFilter.Meta):
        fields = ["q", *BookFilter.Meta.fields]
        form = CatalogFilterForm

    def search(self, queryset, name, value):
        return queryset.filter(Q(title__icontains=value) | Q(author__name__icontains=value))

    # ------------------------------------------------------------------
    # Chips: the active filters above the list, "x" removes one
    # ------------------------------------------------------------------

    def chips(self, currency_symbol):
        """[{"label": ..., "url": ...}] of every chosen value, in the panel order.

        Only the values that passed the form: a wrong one (an old link to a
        deleted category) has its error in the panel, not a chip. The url is
        the current one without this value (and without the page number:
        the shorter list starts from page 1).
        """
        if not self.is_bound:
            return []
        self.errors  # validation first: cleaned_data appears after it
        data = self.form.cleaned_data
        chips = []
        if data.get("q"):
            chips.append(self._chip(_("Search: “%(text)s”") % {"text": data["q"]}, "q"))
        for category in data.get("category") or []:
            chips.append(self._chip(category.name, "category", value=category.slug))
        for author in data.get("author") or []:
            chips.append(self._chip(author.name, "author", value=str(author.pk)))
        if data.get("stock"):
            label = dict(BookQuerySet.STOCK_STATUS_CHOICES)[data["stock"]]
            chips.append(self._chip(label, "stock"))
        price_min, price_max = data.get("price_min"), data.get("price_max")
        if price_min is not None or price_max is not None:
            if price_max is None:
                text = _("Price: from %(min)s %(symbol)s")
            elif price_min is None:
                text = _("Price: up to %(max)s %(symbol)s")
            else:
                text = _("Price: %(min)s–%(max)s %(symbol)s")
            # normalize(): 100.00 -> "100", 99.50 -> "99.5"
            label = text % {
                "min": _plain(price_min),
                "max": _plain(price_max),
                "symbol": currency_symbol,
            }
            chips.append(self._chip(label, "price_min", "price_max"))
        return chips

    def reset_url(self):
        """ "Clear all": the url without any filter; sort and "Per page" stay."""
        return self._url_without(*self.filters)

    def _chip(self, label, *names, value=None):
        return {"label": label, "url": self._url_without(*names, value=value)}

    def _url_without(self, *names, value=None):
        """The current query string without these parameters (or one value of one)."""
        params = self.data.copy()  # a QueryDict of request.GET, mutable copy
        params.pop("page", None)
        for name in names:
            if value is None:
                params.pop(name, None)
            else:
                params.setlist(name, [item for item in params.getlist(name) if item != value])
        return f"?{params.urlencode()}"


def _plain(number):
    """A price of the chip without extra zeros: 100.00 -> 100, 99.50 -> 99.5."""
    return "" if number is None else format(number.normalize(), "f")
