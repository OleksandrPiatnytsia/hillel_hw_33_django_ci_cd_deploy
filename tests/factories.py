"""factory-boy factories: test objects in one line, with sensible defaults.

    BookFactory()                       a book with a new author, 10 in stock
    BookFactory(stock=0, price="99.90") override any field (stock: a Stock row)
    BookFactory(categories=[fiction])   ManyToMany through BookCategory
    UserFactory(groups=["Managers"])    groups by name (made by migrations)
    OrderFactory(user=ann, items=[(book, 2)])   an order with its lines and total

Factory(...) saves to the test database (needs the `db` fixture);
Factory.build(...) only creates the object in memory (no database).
Sequence: a different value for every object (user0, user1, ...), so
unique fields never clash.
"""

from decimal import Decimal

import factory
from django.contrib.auth.models import Group
from factory.django import DjangoModelFactory, Password

from books.models import Author, Book, Category
from inventory.services import set_stock
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
    def stock(self, create, extracted, **kwargs):
        """BookFactory(stock=3): copies in the default warehouse (default 10).

        Not a model field any more (inventory.Stock), so not a plain
        attribute: Book(stock=3) would only set the value of the object.
        create(): a real Stock row; build(): only the value of the object,
        no database (book.is_low_stock still works).
        """
        quantity = 10 if extracted is None else extracted
        if create:
            set_stock(self, quantity)
        else:
            self.stock = quantity

    @factory.post_generation
    def categories(self, create, extracted, **kwargs):
        """BookFactory(categories=[cat1, cat2]); through model, so .add() works
        (Django creates the BookCategory rows)."""
        if not create or not extracted:
            return
        self.categories.add(*extracted)


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
        for book, quantity in extracted:
            OrderItemFactory(order=self, book=book, quantity=quantity)
        self.total = sum(item.cost for item in self.items.all())
        self.save(update_fields=["total", "updated_at"])


class OrderItemFactory(DjangoModelFactory):
    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    book = factory.SubFactory(BookFactory)
    # Copies of the book data, as create_order() makes them
    title = factory.LazyAttribute(lambda item: item.book.title)
    price = factory.LazyAttribute(lambda item: item.book.price)
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
    status = Payment.Status.PENDING
