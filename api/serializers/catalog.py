"""Serializers of the catalog: Python objects <-> JSON, plus validation.

A serializer works in two directions:
    reading   Book object  -> serializer.data (dict)  -> JSON answer
    writing   JSON request -> serializer.is_valid()   -> serializer.save()

Nested serializers: a book shows its author and categories as objects,
not only as numbers, so a client builds a catalog page from one request:

    {"id": 7, "title": "Kobzar",
     "author": {"id": 3, "name": "Taras Shevchenko"},
     "categories": [{"id": 1, "name": "Poetry", "slug": "poetry"}], ...}

For writing the client sends only the ids: "author_id": 3,
"category_ids": [1, 2]. Writable nested objects ("create the author
together with the book") would need our own create()/update(); authors
and categories have their own endpoints for that.

The formats of a book (paper, e-book, audiobook, each with its own
price) are nested in the book for reading and written through their own
endpoint /api/formats/ (BookFormatSerializer): one simple request per
format instead of a list in the book where a missing row would mean
"delete it".
"""

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from books.models import Author, Book, BookFormat, Category, Publisher
from currencies.models import BASE_CURRENCY, Currency
from currencies.services import RateUnavailable, convert
from inventory.services import set_stock


class BooksCountMixin(serializers.Serializer):
    """books_count: the number of books of an author / a category.

    Lists and single objects come from the queryset of the ViewSet with
    .annotate(books_count=Count("books")): one query for the whole page
    instead of a COUNT for every row. An object made by POST is not from
    that queryset and has no such attribute: then one COUNT for it.
    """

    books_count = serializers.SerializerMethodField()

    def get_books_count(self, obj) -> int:
        if hasattr(obj, "books_count"):
            return obj.books_count
        return obj.books.count()


class CategorySerializer(BooksCountMixin, serializers.ModelSerializer):
    """/api/categories/: a category with the number of its books."""

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "books_count"]


class AuthorSerializer(BooksCountMixin, serializers.ModelSerializer):
    """/api/authors/: an author with the number of their books."""

    class Meta:
        model = Author
        fields = ["id", "name", "bio", "books_count"]


class PublisherSerializer(BooksCountMixin, serializers.ModelSerializer):
    """/api/publishers/: a publisher with the number of its books."""

    class Meta:
        model = Publisher
        fields = ["id", "name", "books_count"]


class PublisherShortSerializer(serializers.ModelSerializer):
    """The publisher inside a book."""

    class Meta:
        model = Publisher
        fields = ["id", "name"]


class AuthorShortSerializer(serializers.ModelSerializer):
    """The author inside a book: only what a list of books needs."""

    class Meta:
        model = Author
        fields = ["id", "name"]


class CategoryShortSerializer(serializers.ModelSerializer):
    """A category inside a book."""

    class Meta:
        model = Category
        fields = ["id", "name", "slug"]


def validate_offered_currency(value, current):
    """A turned off currency only for an object that already has it.

    Like the forms on the site: a PUT sends back every field it read, and
    a format priced in a currency turned off later must stay editable.
    """
    if not value.is_active and value.code != current:
        raise serializers.ValidationError(
            _("The currency %(code)s is turned off.") % {"code": value.code}
        )
    return value


def converted_price(book_format, context):
    """The price of a format in the currency of ?currency= (UAH without it); None without a rate."""
    target = context.get("display_currency", BASE_CURRENCY)
    rates = context.get("rates")
    try:
        return convert(book_format.price, book_format.currency_id, target, rates)
    except RateUnavailable:
        return None


class BookFormatSerializer(serializers.ModelSerializer):
    """/api/formats/: one way to buy a book (paper, e-book, audiobook) with its own price.

        {"id": 12, "book_id": 7, "format_type": "paper",
         "format_type_display": "Паперова", "price": "350.00",
         "currency": "UAH", "display_price": "7.71", "display_currency": "USD",
         "cover_type": "hard", "pages": 640, "is_active": true,
         "stock": 10, "in_stock": true}

    Writing:
        book_id, format_type   only when the format is created: the stock
                               rows and the copies of the type in the
                               orders point to them. Another type = a new
                               format (and this one turned off or deleted).
        cover_type             only for paper; pages: not for an audiobook
                               (the same rules as BookFormat.clean())
        stock                  only for paper (a file has no copies) and
                               only with inventory.change_stock (Managers);
                               null for an e-book or an audiobook
    """

    book_id = serializers.PrimaryKeyRelatedField(source="book", queryset=Book.objects.all())
    format_type_display = serializers.CharField(source="get_format_type_display", read_only=True)
    # A code ("UAH", "USD"); not required: UAH by default (the model default)
    currency = serializers.SlugRelatedField(
        slug_field="code", queryset=Currency.objects.all(), required=False
    )
    # Set in to_representation() (converted_price): the same number the
    # format tile of the site shows with the currency switcher
    display_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, allow_null=True
    )
    display_currency = serializers.SerializerMethodField()
    # max_value: the largest PositiveIntegerField value in PostgreSQL;
    # allow_null: an e-book answers null, and a client may send it back
    stock = serializers.IntegerField(
        min_value=0, max_value=2147483647, required=False, allow_null=True
    )
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = BookFormat
        fields = [
            "id",
            "book_id",
            "format_type",
            "format_type_display",
            "price",
            "currency",
            "display_price",
            "display_currency",
            "cover_type",
            "pages",
            "is_active",
            "stock",
            "in_stock",
        ]
        # No automatic validator from UniqueConstraint(book, format_type):
        # validate() answers on "format_type" with the text of the model
        validators = []

    def get_display_currency(self, book_format) -> str:
        return self.context.get("display_currency", BASE_CURRENCY)

    def to_representation(self, book_format):
        book_format.display_price = converted_price(book_format, self.context)
        data = super().to_representation(book_format)
        if not book_format.is_paper:
            data["stock"] = None  # a file has no copies, not "0 copies"
        return data

    def validate_currency(self, value):
        return validate_offered_currency(
            value, self.instance.currency_id if self.instance else None
        )

    def validate_stock(self, value):
        """Only users with inventory.change_stock may CHANGE the stock.

        Sending the current value is allowed: a client that edits a format
        with PUT sends back every field it has read, the stock too (null
        for a file). New format: the current value is 0 (its new Stock row).
        """
        request = self.context.get("request")
        if value is None or request is None or request.user.has_perm("inventory.change_stock"):
            return value
        current = self.instance.stock if self.instance else 0
        if value != current:
            # 403, not 400: the value is fine, the user is not allowed
            raise PermissionDenied(
                _("Only users with the “manage stock” permission can change it.")
            )
        return value

    def validate(self, attrs):
        """The rules of BookFormat.clean() + one format of a type per book.

        A ModelSerializer doesn't call the model's clean(). PATCH may send
        only some fields: the others are the current values of the format.
        """
        attrs = super().validate(attrs)
        instance = self.instance

        def value(name, default):
            if name in attrs:
                return attrs[name]
            return getattr(instance, name) if instance else default

        errors = {}
        if instance is not None:
            # The same value is allowed: PUT sends back what it read
            if "book" in attrs and attrs["book"].pk != instance.book_id:
                errors["book_id"] = [_("The book of a format can't be changed.")]
            if "format_type" in attrs and attrs["format_type"] != instance.format_type:
                errors["format_type"] = [
                    _("The type of a format can't be changed; add a new format instead.")
                ]
        format_type = value("format_type", "")
        paper = format_type == BookFormat.FormatType.PAPER
        if value("cover_type", "") and not paper:
            errors["cover_type"] = [_("Only a paper book has a cover type.")]
        if value("pages", None) and format_type == BookFormat.FormatType.AUDIOBOOK:
            errors["pages"] = [_("An audiobook has no pages.")]
        if attrs.get("stock") and not paper:
            errors["stock"] = [_("Only a paper book has copies in stock.")]
        if instance is None and "book" in attrs and "format_type" not in errors:
            if attrs["book"].formats.filter(format_type=format_type).exists():
                errors["format_type"] = [_("The book already has this format.")]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        # BookFormat(**validated_data) would only put the number into the
        # object: take it out and write it to the default warehouse
        stock = validated_data.pop("stock", None)
        book_format = super().create(validated_data)
        if stock:  # None or 0: the row made by inventory.signals already has 0
            set_stock(book_format, stock)
        return book_format

    def update(self, instance, validated_data):
        stock = validated_data.pop("stock", None)
        book_format = super().update(instance, validated_data)
        # Only a value different from the current one is written: PUT sends
        # back every field it read, and an unchanged stock needs no UPDATE.
        # Like any PUT without a version check (ETag / If-Match), a stock
        # changed by an order between the client's GET and its PUT can
        # still be overwritten by the old number.
        if stock is not None and book_format.is_paper and stock != book_format.stock:
            set_stock(book_format, stock)
        return book_format


class BookFormatInBookSerializer(BookFormatSerializer):
    """A format inside a book: the same fields without book_id (it is the book's id)."""

    class Meta(BookFormatSerializer.Meta):
        fields = [name for name in BookFormatSerializer.Meta.fields if name != "book_id"]
        read_only_fields = fields


class BookSerializer(serializers.ModelSerializer):
    """/api/books/: read with nested author, categories and formats, write with ids.

    The prices, the types, the covers, the pages and the stock belong to
    the formats (BookFormat): a book is sold as paper, e-book and
    audiobook, each with its own price. "formats" lists the formats on
    sale (read only); they are written through /api/formats/.

        {"id": 7, "title": "Kobzar", ...,
         "display_price": "149.00", "display_currency": "UAH",
         "formats": [{"id": 11, "format_type": "paper", "price": "350.00", ...},
                     {"id": 12, "format_type": "ebook", "price": "149.00", ...}],
         "in_stock": true}

    display_price: the price "from" (the cheapest format on sale) in the
    currency of ?currency=, like the card of the site; null when no format
    is on sale. A new book has no formats: it is not on sale until the
    first format is added (POST /api/formats/).
    """

    # Reading: nested objects (read_only: they are never parsed from a request)
    author = AuthorShortSerializer(read_only=True)
    categories = CategoryShortSerializer(many=True, read_only=True)
    # null for a book without a publisher
    publisher = PublisherShortSerializer(read_only=True)
    # Book.active_formats: from the Prefetch of BookViewSet (with the
    # stock), one query for the whole page
    formats = BookFormatInBookSerializer(source="active_formats", many=True, read_only=True)

    # Writing: ids. source= points to the model field; the serializer finds
    # the objects itself and answers 400 for an unknown id:
    #   {"author_id": ["Invalid pk \"999\" - object does not exist."]}
    author_id = serializers.PrimaryKeyRelatedField(
        source="author", queryset=Author.objects.all(), write_only=True
    )
    category_ids = serializers.PrimaryKeyRelatedField(
        source="categories",
        queryset=Category.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )
    # null: the publisher is not known (or is removed by PATCH)
    publisher_id = serializers.PrimaryKeyRelatedField(
        source="publisher",
        queryset=Publisher.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    # The price "from" in the currency of ?currency= (UAH without it), at
    # today's NBU rate: the annotation of BookViewSet (with_display_price).
    # Read only; null without a format on sale (or without a rate).
    display_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, allow_null=True
    )
    display_currency = serializers.SerializerMethodField()

    # Absolute URL of the uploaded cover, null without one. Read only:
    # covers are uploaded on the site (BookForm checks size and type)
    cover = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "author",
            "author_id",
            "categories",
            "category_ids",
            "display_price",
            "display_currency",
            "description",
            # The details of the edition; language is a code ("uk"), the API
            # documentation lists them
            "publisher",
            "publisher_id",
            "language",
            "publication_year",
            "formats",
            "in_stock",
            "cover",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_cover(self, book) -> str | None:
        # The "-> str | None" hint: drf-spectacular takes the type for the
        # documentation from it (a method field has no model field behind it)
        if not book.cover:
            return None
        request = self.context.get("request")
        url = book.cover.url
        # http://host/media/covers/...: an API client is not on our site and
        # can't resolve "/media/..." by itself
        return request.build_absolute_uri(url) if request else url

    def get_in_stock(self, book) -> bool:
        # Can it be bought: a digital format on sale, or paper with copies
        return book.available

    def get_display_currency(self, book) -> str:
        # Set by BookViewSet (the checked ?currency=); a serializer used
        # elsewhere shows the prices in UAH
        return self.context.get("display_currency", BASE_CURRENCY)

    def to_representation(self, book):
        # A book just made by POST is not from the annotated queryset of the
        # ViewSet: its price "from" is the cheapest of its formats on sale
        # (none for a new book). Formats without a rate only when nothing else.
        if not hasattr(book, "display_price"):
            prices = [converted_price(f, self.context) for f in book.active_formats]
            known = [price for price in prices if price is not None]
            book.display_price = min(known) if known else None
        return super().to_representation(book)
