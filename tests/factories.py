"""factory-boy factories: test objects in one line, with sensible defaults.

    BookFactory()                       a book with a new author, one paper format, 10 in stock
    BookFactory(stock=0, price="99.90") override any field (stock: a Stock row of the paper format)
    BookFactory(categories=[fiction])   ManyToMany through BookCategory
    BookFactory(formats=False)          a book without formats (by default: one, from its price)
    BookFormatFactory(book=book, format_type="ebook")   one more format of a book
    BookFormatFactory(stock=2)          a paper format with 2 copies (default 10)
    UserFactory(groups=["Managers"])    groups by name (made by migrations)
    OrderFactory(user=ann, items=[(book, 2)])   an order with its lines and total
                                        (book: its first format; or a BookFormat)

Factory(...) saves to the test database (needs the `db` fixture);
Factory.build(...) only creates the object in memory (no database).
Sequence: a different value for every object (user0, user1, ...), so
unique fields never clash.
"""

from decimal import Decimal

import factory
from django.contrib.auth.models import Group
from factory.django import DjangoModelFactory, Password

from books.models import Author, Book, BookFormat, Category
from inventory.services import paper_format_of, set_stock
from orders.models import Order, OrderItem
from payments.models import Payment
from users.models import User

# Password of every user from UserFactory: client.login(username=..., password=...)
DEFAULT_PASSWORD = "Test-pass-123"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        # The post_generation hook below saves what it changes itself;
        # without this flag factory-boy would call save() once more
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda user: f"{user.username}@example.com")
    first_name = "Ann"
    last_name = "Shevchenko"
    # Password(): hashes the text with set_password() (the fast MD5 hasher
    # from config/settings/test.py), the same as create_user()
    password = Password(DEFAULT_PASSWORD)

    @factory.post_generation
    def groups(self, create, extracted, **kwargs):
        """UserFactory(groups=["Managers"]): add the user to these groups."""
        if not create or not extracted:
            return
        self.groups.add(*Group.objects.filter(name__in=extracted))


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = Category
        # CategoryFactory(name="Fiction") twice -> the same row, not an error
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")


class AuthorFactory(DjangoModelFactory):
    class Meta:
        model = Author
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Author {n}")
    bio = "A writer."


class BookFactory(DjangoModelFactory):
    class Meta:
        model = Book
        skip_postgeneration_save = True

    title = factory.Sequence(lambda n: f"Book {n}")
    # SubFactory: a new Author for every book unless one is given
    author = factory.SubFactory(AuthorFactory)
    price = Decimal("250.00")
    description = "A good book."

    @factory.post_generation
    def formats(self, create, extracted, **kwargs):
        """One format on sale, from the book's own fields (like the data migration 0014).

        BookFactory(formats=False): a book without any format (not on sale,
        or a test that adds its own with BookFormatFactory).
        build(): nothing, no database.
        """
        if not create or extracted is False:
            return
        paper = self.book_type == Book.BookType.PAPER
        self.formats.create(
            format_type=self.book_type,
            price=self.price,
            currency_id=self.currency_id,
            cover_type=self.cover_type if paper else "",
            pages=None if self.book_type == Book.BookType.AUDIOBOOK else self.pages,
        )

    @factory.post_generation
    def stock(self, create, extracted, **kwargs):
        """BookFactory(stock=3): copies of its paper format in the default warehouse (default 10).

        Not a model field (inventory.Stock of the paper format), so not a
        plain attribute: Book(stock=3) would only set the value of the
        object. Runs after formats() (hooks run in the order they are
        declared): the paper format must exist first. create(): a real
        Stock row, only for a book with a paper format (an e-book has no
        copies); build(): only the value of the object, no database
        (book.is_low_stock still works).
        """
        quantity = 10 if extracted is None else extracted
        if not create:
            self.stock = quantity
        elif paper_format_of(self) is not None:
            set_stock(self, quantity)

    @factory.post_generation
    def categories(self, create, extracted, **kwargs):
        """BookFactory(categories=[cat1, cat2]); through model, so .add() works
        (Django creates the BookCategory rows)."""
        if not create or not extracted:
            return
        self.categories.add(*extracted)


class BookFormatFactory(DjangoModelFactory):
    """BookFormatFactory(book=book, format_type="ebook", price="199.00")."""

    class Meta:
        model = BookFormat
        skip_postgeneration_save = True

    # A book without its own default format: the test says which ones it has
    book = factory.SubFactory(BookFactory, formats=False)
    format_type = BookFormat.FormatType.PAPER
    price = Decimal("250.00")

    @factory.post_generation
    def stock(self, create, extracted, **kwargs):
        """Copies of a paper format (default 10); an e-book has none."""
        if create and self.is_paper:
            set_stock(self, 10 if extracted is None else extracted)


class OrderFactory(DjangoModelFactory):
    """An order as it is in the database, WITHOUT the checkout logic.

    The stock of the books is not reserved here: for unit tests of the model
    and the pages. Tests of the checkout itself call
    orders.services.create_order() (the real code).
    """

    class Meta:
        model = Order
        skip_postgeneration_save = True

    user = factory.SubFactory(UserFactory)
    full_name = "Ann Shevchenko"
    phone = "+380671234567"
    address = "Kyiv, Khreshchatyk 1"
    total = Decimal("0.00")

    @factory.post_generation
    def items(self, create, extracted, **kwargs):
        """OrderFactory(items=[(book, 2), (other_book, 1)]): lines + total."""
        if not create or not extracted:
            return
        for target, quantity in extracted:
            if isinstance(target, BookFormat):
                OrderItemFactory(order=self, book=target.book, format=target, quantity=quantity)
            else:
                OrderItemFactory(order=self, book=target, quantity=quantity)
        self.total = sum(item.cost for item in self.items.all())
        self.save(update_fields=["total", "updated_at"])


class OrderItemFactory(DjangoModelFactory):
    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    book = factory.SubFactory(BookFactory)
    # The first format of the book (paper first): BookFactory makes one
    format = factory.LazyAttribute(lambda item: item.book.formats.first())
    # Copies of the book data, as create_order() makes them
    format_type = factory.LazyAttribute(lambda item: item.format.format_type)
    title = factory.LazyAttribute(lambda item: item.book.title)
    price = factory.LazyAttribute(lambda item: item.book.price)
    # Not converted: the book in the currency of the order (UAH by default)
    original_price = factory.LazyAttribute(lambda item: item.price)
    original_currency_id = factory.LazyAttribute(lambda item: item.order.currency_id)
    exchange_rate = Decimal("1")
    quantity = 1


class PaymentFactory(DjangoModelFactory):
    """A pending Stripe payment for the whole order (amount = order.total).

    The order's payment_status is NOT recalculated here; tests that need it
    call payments.services (the real code) or order.refresh_payment_status().
    """

    class Meta:
        model = Payment

    order = factory.SubFactory(OrderFactory, total=Decimal("250.00"))
    provider = Payment.Provider.STRIPE
    external_id = factory.Sequence(lambda n: f"cs_test_{n}")
    amount = factory.LazyAttribute(lambda payment: payment.order.total)
    currency_id = factory.LazyAttribute(lambda payment: payment.order.currency_id)
    status = Payment.Status.PENDING
