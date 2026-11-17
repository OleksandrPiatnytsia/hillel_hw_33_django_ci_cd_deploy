"""Filters of the book catalog (django-filter), one set for the site and the API.

BookFilter turns GET parameters into .filter() calls:
    ?category=fantasy&category=poetry&author=3&author=7&stock=in_stock&price_min=100
    ?publisher=5&language=uk&language=en&book_type=ebook&cover_type=hard&year_min=2015

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

from .models import Author, Book, BookCategory, BookFormat, BookQuerySet, Category, Publisher


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
    publisher = django_filters.ModelMultipleChoiceFilter(
        queryset=Publisher.objects.all(),  # ?publisher=<pk>
        method="filter_any_of",
        label=_("Publisher"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    # The choices of the model (Book.Language, ...): the value in the URL is
    # the code (?language=uk), the panel shows the translated label
    language = django_filters.MultipleChoiceFilter(
        choices=Book.Language.choices,
        method="filter_any_of",
        label=_("Language"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    # The formats on sale (BookFormat): ?book_type=ebook -> the books that
    # can be bought as an e-book. Not "?format=": the API (DRF) keeps that
    # name for the format of the answer (?format=json), and "book_type" is
    # the name the filter had before the formats, so old links still work.
    book_type = django_filters.MultipleChoiceFilter(
        field_name="formats__format_type",
        choices=BookFormat.FormatType.choices,
        method="filter_format",
        label=_("Format"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    # The cover of the paper format on sale
    cover_type = django_filters.MultipleChoiceFilter(
        field_name="formats__cover_type",
        choices=BookFormat.CoverType.choices,
        method="filter_cover",
        label=_("Cover"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    # A range like the price; a book without a year is not in any range
    year_min = django_filters.NumberFilter(
        field_name="publication_year",
        lookup_expr="gte",
        min_value=0,
        label=_("Year from"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
    )
    year_max = django_filters.NumberFilter(
        field_name="publication_year",
        lookup_expr="lte",
        min_value=0,
        label=_("Year to"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
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
        # The order of the blocks in the panel
        fields = [
            "category",
            "author",
            "publisher",
            "language",
            "book_type",
            "cover_type",
            "year_min",
            "year_max",
            "stock",
            "price_min",
            "price_max",
        ]

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

    def filter_any_of(self, queryset, name, value):
        """One of the chosen values: publisher, language.

        A field of the book itself (no JOIN): IN (...) gives no duplicates.
        Not django-filter's own MultipleChoiceFilter filtering: it adds
        .distinct(), which does not go well with the annotations of the list.
        """
        return queryset.filter(**{f"{name}__in": value}) if value else queryset

    def filter_format(self, queryset, name, value):
        # EXISTS, like the categories: a book in two of the chosen formats
        # would come twice with a JOIN
        return self._with_format(queryset, format_type__in=value) if value else queryset

    def filter_cover(self, queryset, name, value):
        # A cover is a thing of the paper format only (BookFormat.clean())
        if not value:
            return queryset
        return self._with_format(
            queryset, format_type=BookFormat.FormatType.PAPER, cover_type__in=value
        )

    @staticmethod
    def _with_format(queryset, **conditions):
        """The books with a format on sale that matches the conditions."""
        matching = BookFormat.objects.filter(book=OuterRef("pk"), is_active=True, **conditions)
        return queryset.filter(Exists(matching))

    def filter_stock(self, queryset, name, value):
        # The rule "low = 1..5" lives in one place, the model's queryset
        return queryset.by_stock_status(value)


# The ranges of the filters: (from, to, the error of "from > to")
RANGES = [
    ("price_min", "price_max", _("“Price from” can't be greater than “Price to”.")),
    ("year_min", "year_max", _("“Year from” can't be greater than “Year to”.")),
]


def wrong_ranges(cleaned_data):
    """[(from, to, error)] of the ranges where "from" is greater than "to"."""
    wrong = []
    for low_name, high_name, error in RANGES:
        low, high = cleaned_data.get(low_name), cleaned_data.get(high_name)
        if low is not None and high is not None and low > high:
            wrong.append((low_name, high_name, error))
    return wrong


class CatalogFilterForm(forms.Form):
    """The form of the site's catalog: a wrong range is skipped.

    "Price from 500 to 100" (or "year from 2020 to 2010") would always give
    an empty list: both ends are taken out of cleaned_data (the catalog
    ignores them and applies the other filters) and the hint is shown above
    the filters. The API answers such a range with 400 instead
    (api.filters.BookFilterForm).
    """

    def clean(self):
        cleaned_data = super().clean()
        for low_name, high_name, error in wrong_ranges(cleaned_data):
            del cleaned_data[low_name], cleaned_data[high_name]
            self.add_error(None, error)
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
        # The average of the customers' stars (BookQuerySet.with_rating)
        ("-rating", _("Best rated")),
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

    # The blocks of the panel offer only the values some book has: 32
    # publishers from the migration, but a catalog of 12 books has 5 of
    # them; 6 languages, but the books are in 2. A block without values is
    # not shown at all (books/book_list.html).
    VALUES_IN_USE = ["language"]
    # The same for the formats: the values of the formats on sale
    FORMAT_VALUES_IN_USE = {"book_type": "format_type", "cover_type": "cover_type"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        fields = self.form.fields
        # A value nobody has (an old link) is then an error of the panel,
        # like a deleted category; the API accepts every publisher
        fields["publisher"].queryset = Publisher.objects.filter(
            Exists(Book.objects.filter(publisher=OuterRef("pk")))
        )
        for name in self.VALUES_IN_USE:
            in_use = set(Book.objects.exclude(**{name: ""}).values_list(name, flat=True).distinct())
            self._keep_choices(name, in_use)
        active_formats = BookFormat.objects.filter(is_active=True)
        for name, format_field in self.FORMAT_VALUES_IN_USE.items():
            in_use = set(active_formats.values_list(format_field, flat=True).distinct())
            self._keep_choices(name, in_use)

    def _keep_choices(self, name, in_use):
        field = self.form.fields[name]
        field.choices = [(value, label) for value, label in field.choices if value in in_use]

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
        for publisher in data.get("publisher") or []:
            chips.append(self._chip(publisher.name, "publisher", value=str(publisher.pk)))
        for name in ["language", "book_type", "cover_type"]:
            labels = dict(self.form.fields[name].choices)
            for value in data.get(name) or []:
                chips.append(self._chip(labels[value], name, value=value))
        year_min, year_max = data.get("year_min"), data.get("year_max")
        if year_min is not None or year_max is not None:
            if year_max is None:
                text = _("Year: from %(min)s")
            elif year_min is None:
                text = _("Year: up to %(max)s")
            else:
                text = _("Year: %(min)s–%(max)s")
            label = text % {"min": _plain(year_min), "max": _plain(year_max)}
            chips.append(self._chip(label, "year_min", "year_max"))
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
