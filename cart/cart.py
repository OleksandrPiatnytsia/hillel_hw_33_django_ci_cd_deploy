from decimal import Decimal

from books.models import Book

# Key of the cart in request.session
CART_SESSION_KEY = "cart"


class Cart:
    """Shopping cart stored in the session: works for guests and users.

    What is stored (request.session["cart"]):
        {"<book_id>": {"quantity": 2}, "<book_id>": {"quantity": 1}}
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
        cart.add(book, quantity=2)
        for item in cart: item["book"], item["quantity"], item["cost"]
        len(cart), cart.total
    """

    def __init__(self, request):
        self.session = request.session
        # A new dict is NOT written to the session here: the cart appears in
        # the session only after the first add(), so visitors who never buy
        # anything don't get a cart in their session.
        self.cart = self.session.get(CART_SESSION_KEY, {})
        # Cache of the items with Book objects, filled by _get_items():
        # the template reads the items and the total -> one SQL query, not two
        self._items = None

    # ------------------------------------------------------------------
    # Changes
    # ------------------------------------------------------------------

    def add(self, book, quantity=1, override=False):
        """Add `quantity` copies of the book, or set the quantity (override=True).

        - override=False: "Add to cart" button, 2 in the cart + 1 = 3;
        - override=True: the quantity field on the cart page, set to exactly 1.
        The result is limited by book.stock: the cart can't hold more copies
        than the store has. With stock 0 the book is removed from the cart.

        Returns the quantity of the book in the cart after the change
        (0 = not in the cart), so the view can show the right message.
        """
        key = str(book.pk)
        current = self.cart.get(key, {}).get("quantity", 0)
        wanted = quantity if override else current + quantity
        new_quantity = min(wanted, book.stock)

        if new_quantity <= 0:
            self.remove(book)
            return 0

        self.cart[key] = {"quantity": new_quantity}
        self._save()
        return new_quantity

    def remove(self, book):
        """Remove the book from the cart (all copies)."""
        key = str(book.pk)
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
        # (session["cart"] = ...). Changes inside the nested dict
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
        """List of items with Book objects and costs; one SQL query, cached."""
        if self._items is not None:
            return self._items

        # in_bulk: {id: Book} for all ids of the cart in one query
        # (WHERE id IN (...)); select_related: author names in the same query;
        # with_stock(): the stock in the same query too
        books = (
            Book.objects.select_related("author")
            .with_stock()
            .in_bulk([int(key) for key in self.cart])
        )

        items = []
        removed = False
        for key, data in list(self.cart.items()):
            book = books.get(int(key))
            if book is None:
                # The book was deleted after it was put into the cart
                del self.cart[key]
                removed = True
                continue
            quantity = data["quantity"]
            items.append(
                {
                    "book": book,
                    "quantity": quantity,
                    "price": book.price,  # the current price from the database
                    "cost": book.price * quantity,
                    # The stock may have dropped since the book was added
                    # (someone else bought it). Checkout (stage 3) checks it
                    # again under a lock; here it's only a warning in the cart.
                    "exceeds_stock": quantity > book.stock,
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
    def total(self):
        """Sum of all items at the current prices, in UAH."""
        # start: an empty cart gives Decimal("0.00"), not the int 0
        return sum((item["cost"] for item in self._get_items()), start=Decimal("0.00"))

    def quantities(self):
        """{book_id: quantity} — the cart as plain data for checkout.

        orders.services gets only this dict: it doesn't need to know how the
        cart is stored, and it reads prices and stock from the database itself.
        """
        return {int(key): data["quantity"] for key, data in self.cart.items()}

    def quantity_of(self, book):
        """How many copies of this book are in the cart (0 if none)."""
        return self.cart.get(str(book.pk), {}).get("quantity", 0)
