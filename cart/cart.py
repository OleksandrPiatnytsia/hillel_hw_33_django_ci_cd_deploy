from decimal import Decimal

from django.db.models import Prefetch

from books.models import Book, BookFormat
from currencies.display import book_price, display_currency

# Key of the cart in request.session: by format
CART_SESSION_KEY = "cart_formats"
# The cart before the formats: {"<book_id>": {"quantity": 2}}. A visitor
# whose session still has it gets it converted once (Cart._convert_old_cart)
OLD_CART_SESSION_KEY = "cart"


class Cart:
    """Shopping cart stored in the session: works for guests and users.

    What is stored (request.session["cart_formats"]):
        {"<format_id>": {"quantity": 2}, "<format_id>": {"quantity": 1}}
    - a line is a FORMAT of a book (paper, e-book, audiobook), each with
      its own price: the same book in two formats is two lines;
    - keys are strings: the session is saved as JSON, and JSON object keys
      are always strings (an int key 15 would come back as "15");
    - only the quantity: the price is read from the database every time,
      so the cart always shows the current price, and nobody can change the
      price by editing the session.

    The session lives on the server (Redis + PostgreSQL, SESSION_ENGINE
    cached_db); the browser only keeps the session id in a cookie.
    On login Django keeps the session data (only the id changes), so a
    guest's cart stays after login. Logout clears the session and the cart.

    Usage:
        cart = Cart(request)
        cart.add(book_format, quantity=2)
        cart.change_format(book_format, other_format)
        for item in cart: item["format"], item["book"], item["quantity"], item["cost"]
        len(cart), cart.total, cart.currency

    Prices, costs and the total are in the currency of the switcher
    (cart.currency): every format is converted from its own currency at the
    current rate, the price of ONE copy is rounded first, then multiplied
    by the quantity (the same rule as the order will use).
    """

    def __init__(self, request):
        self.request = request
        self.session = request.session
        # A new dict is NOT written to the session here: the cart appears in
        # the session only after the first add(), so visitors who never buy
        # anything don't get a cart in their session.
        self.cart = self.session.get(CART_SESSION_KEY, {})
        if OLD_CART_SESSION_KEY in self.session:
            self._convert_old_cart()
        # Cache of the items with BookFormat objects, filled by _get_items():
        # the template reads the items and the total -> one SQL query, not two
        self._items = None

    def _convert_old_cart(self):
        """The cart by book (before the formats) -> the cart by format, once.

        Every book goes to its main format (Book.main_format: the first one
        on sale that can be bought, paper first). A book with no format on
        sale is dropped, like a deleted book. The old key is removed, so
        this runs only on the first request after the release.
        """
        old_cart = self.session.pop(OLD_CART_SESSION_KEY) or {}
        books = Book.objects.with_active_formats().in_bulk(
            [int(key) for key in old_cart if str(key).isdigit()]
        )
        for key, data in old_cart.items():
            book = books.get(int(key)) if str(key).isdigit() else None
            book_format = book.main_format if book is not None else None
            if book_format is None:
                continue
            line = self.cart.setdefault(str(book_format.pk), {"quantity": 0})
            line["quantity"] += data.get("quantity", 0)
        self._save()

    # ------------------------------------------------------------------
    # Changes
    # ------------------------------------------------------------------

    def add(self, book_format, quantity=1, override=False):
        """Add `quantity` copies of the format, or set the quantity (override=True).

        - override=False: "Add to cart" button, 2 in the cart + 1 = 3;
        - override=True: the quantity field on the cart page, set to exactly 1.
        A paper book is limited by its stock: the cart can't hold more
        copies than the store has; with stock 0 it is removed from the cart.
        An e-book or an audiobook has no limit. A format that is not on sale
        is removed.

        Returns the quantity of the format in the cart after the change
        (0 = not in the cart), so the view can show the right message.
        """
        key = str(book_format.pk)
        current = self.cart.get(key, {}).get("quantity", 0)
        wanted = quantity if override else current + quantity
        limit = book_format.max_quantity
        new_quantity = wanted if limit is None else min(wanted, limit)
        if not book_format.is_active:
            new_quantity = 0

        if new_quantity <= 0:
            self.remove(book_format)
            return 0

        self.cart[key] = {"quantity": new_quantity}
        self._save()
        return new_quantity

    def change_format(self, book_format, new_format):
        """Move the line of book_format to new_format (another format of the same book).

        The quantity goes along; if new_format is already in the cart, the
        two lines become one (2 + 1 = 3). The limits of add() apply: a paper
        book gets at most its stock. Returns the new quantity (0 = the new
        format can't be bought, the old line is kept).
        """
        quantity = self.cart.get(str(book_format.pk), {}).get("quantity", 0)
        if quantity == 0 or book_format.pk == new_format.pk:
            return quantity
        new_quantity = self.add(new_format, quantity)
        if new_quantity:
            self.remove(book_format)
        return new_quantity

    def remove(self, book_format):
        """Remove the format from the cart (all copies)."""
        key = str(book_format.pk)
        if key in self.cart:
            del self.cart[key]
            self._save()

    def clear(self):
        """Empty the cart: after checkout or with the "Clear cart" button."""
        self.session.pop(CART_SESSION_KEY, None)
        self.cart = {}
        self._items = None

    def _save(self):
        # The session notices only assignments to its own keys
        # (session["cart_formats"] = ...). Changes inside the nested dict
        # (self.cart["15"] = ...) are invisible to it, so the assignment
        # below is always done. modified=True tells the session middleware
        # to write the session at the end of the request.
        self.session[CART_SESSION_KEY] = self.cart
        self.session.modified = True
        self._items = None  # the cached items are out of date

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def _get_items(self):
        """List of items with BookFormat objects and costs; two SQL queries, cached."""
        if self._items is not None:
            return self._items

        # in_bulk: {id: BookFormat} for all ids of the cart in one query
        # (WHERE id IN (...)); select_related: the book and its author in the
        # same query; with_stock(): the stock of the paper books too.
        # The Prefetch: the formats on sale of every book (the "Format"
        # select of the cart page) in one more query.
        formats = (
            BookFormat.objects.select_related("book__author")
            .with_stock()
            .prefetch_related(
                Prefetch(
                    "book__formats",
                    queryset=BookFormat.objects.filter(is_active=True),
                    to_attr="prefetched_active_formats",
                )
            )
            .in_bulk([int(key) for key in self.cart])
        )

        items = []
        removed = False
        for key, data in list(self.cart.items()):
            book_format = formats.get(int(key))
            if book_format is None:
                # The format (or its book) was deleted after it was put
                # into the cart
                del self.cart[key]
                removed = True
                continue
            quantity = data["quantity"]
            # The current price from the database, in the switcher's currency
            price = book_price(self.request, book_format).amount
            book = book_format.book
            items.append(
                {
                    "format": book_format,
                    "book": book,
                    "quantity": quantity,
                    "price": price,
                    "cost": price * quantity,
                    # Switched off after it was added: checkout refuses it,
                    # the cart page offers the other formats
                    "not_on_sale": not book_format.is_active,
                    # The stock may have dropped since the book was added
                    # (someone else bought it). Checkout checks it again
                    # under a lock; here it's only a warning in the cart.
                    "exceeds_stock": book_format.is_paper and quantity > book_format.stock,
                    # The "Format" select: the formats on sale of the book;
                    # the current one too if it is not on sale any more
                    "format_choices": (
                        book.active_formats
                        if book_format.is_active
                        else [book_format, *book.active_formats]
                    ),
                }
            )
        if removed:
            self._save()

        self._items = items
        return items

    def __iter__(self):
        """for item in cart: ... (in templates: {% for item in cart %})."""
        return iter(self._get_items())

    def __len__(self):
        """Number of copies in the cart (2 + 1 = 3), for the navbar counter.

        Reads only the session, no SQL query: the counter is shown on every page.
        """
        return sum(data["quantity"] for data in self.cart.values())

    def __bool__(self):
        # Without it `if cart` would call __len__; explicit is clearer
        return bool(self.cart)

    @property
    def currency(self):
        """The Currency of price / cost / total: the one of the switcher."""
        return display_currency(self.request)

    @property
    def total(self):
        """Sum of all items at the current prices, in cart.currency."""
        # start: an empty cart gives Decimal("0.00"), not the int 0
        return sum((item["cost"] for item in self._get_items()), start=Decimal("0.00"))

    def quantities(self):
        """{format_id: quantity} — the cart as plain data for checkout.

        orders.services gets only this dict: it doesn't need to know how the
        cart is stored, and it reads prices and stock from the database itself.
        """
        return {int(key): data["quantity"] for key, data in self.cart.items()}

    def quantity_of(self, book_format):
        """How many copies of this format are in the cart (0 if none)."""
        return self.cart.get(str(book_format.pk), {}).get("quantity", 0)

    def lines_of(self, book):
        """[(format, quantity), ...]: the formats of this book in the cart.

        Only the formats on sale (book.active_formats, no query for the
        cached book of the book page): "In your cart: Paper — 2".
        """
        lines = [(f, self.quantity_of(f)) for f in book.active_formats]
        return [(f, quantity) for f, quantity in lines if quantity]
