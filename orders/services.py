"""Business logic of orders: create an order from the cart, cancel an order.

Kept out of the views: the same functions are used by the checkout page,
the "Cancel" button, the admin (stage 8) and the cancel_unpaid_orders
command, and the rules (locks, stock) must be the same everywhere.
"""

from functools import partial

from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from books.models import Book
from config.celery import enqueue_on_commit
from inventory.models import Stock, Warehouse
from inventory.services import return_to_stock

from .models import Order, OrderItem
from .tasks import send_order_cancelled_email_task, send_order_created_email_task


class OrderError(Exception):
    """An order can't be created or cancelled; the text is shown to the user."""

    def __init__(self, messages):
        # A list: checkout reports every book with a problem at once,
        # not only the first one
        self.messages = messages if isinstance(messages, list) else [messages]
        super().__init__("; ".join(self.messages))


def create_order(user, quantities, *, full_name, phone, address, idempotency_key=""):
    """Create an order from {book_id: quantity} and reserve the stock.

    idempotency_key: the Idempotency-Key header of the API (the site sends
    none). Saved with the order; a second order of this user with the same
    key raises IntegrityError (unique constraint) and the whole transaction
    is rolled back, the stock too.

    Everything inside transaction.atomic(): either the order, all its items
    and all stock changes are saved together, or nothing (an exception in
    the middle rolls back the whole transaction — no order without items,
    no stock taken for an order that doesn't exist).

    The copies are taken from the default warehouse (inventory.Stock).

    Flow:
    1. Lock the stock rows of the ordered books (SELECT ... FOR UPDATE).
    2. Check that every book exists and has enough stock.
    3. Create the Order and its OrderItems with the current prices.
    4. Reserve: quantity -= ordered for every stock row.
    5. COMMIT: the locks are released.

    Raises OrderError if the cart is empty or something is missing; the
    database stays unchanged then.
    """
    if not quantities:
        raise OrderError(_("The cart is empty."))

    with transaction.atomic():
        warehouse = Warehouse.objects.get_default()

        # select_for_update(): other transactions that want to lock or
        # change these rows WAIT until this one ends. Without the lock two
        # users could both read stock = 1 and both buy the last copy:
        #   A: reads stock 1 -> ok        B: reads stock 1 -> ok
        #   A: stock = 0                  B: stock = 0  (2 copies sold, 1 existed)
        # With the lock B waits on its SELECT, then reads stock 0 -> error.
        #
        # The locked rows are the Stock rows (book + warehouse), not the
        # books: the stock lives there. Editing a book's title or price at
        # the same moment doesn't wait for a checkout.
        #
        # order_by("book_id"): every checkout locks the rows in the same
        # order. Otherwise A could lock book 1 and wait for book 2, while B
        # locked book 2 and waits for book 1 -> deadlock (PostgreSQL would
        # cancel one).
        stocks = {
            stock.book_id: stock
            for stock in Stock.objects.select_for_update()
            .filter(warehouse=warehouse, book_id__in=quantities)
            .order_by("book_id")
        }
        # Title and price, without a lock: OrderItem copies them
        books = Book.objects.in_bulk(list(quantities))

        problems = []
        for book_id, quantity in quantities.items():
            book = books.get(book_id)
            # No row in the default warehouse = nothing to sell
            available = stocks[book_id].quantity if book_id in stocks else 0
            if book is None:
                problems.append(_("A book from your cart is no longer sold."))
            elif available < quantity:
                if available == 0:
                    problems.append(_("“%(title)s” is out of stock.") % {"title": book.title})
                else:
                    # ngettext: the form depends on the number. Ukrainian
                    # has three ("залишився 1 примірник", "2 примірники",
                    # "5 примірників"), English two; the .po file holds them all
                    problems.append(
                        ngettext(
                            "“%(title)s”: only %(stock)s copy left, you ordered %(quantity)s.",
                            "“%(title)s”: only %(stock)s copies left, you ordered %(quantity)s.",
                            available,
                        )
                        % {"title": book.title, "stock": available, "quantity": quantity}
                    )
        if problems:
            # Leaving the "with" block with an exception = ROLLBACK
            # (here nothing was written yet, but the locks are released too)
            raise OrderError(problems)

        order = Order.objects.create(
            user=user,
            full_name=full_name,
            phone=phone,
            address=address,
            idempotency_key=idempotency_key,
        )

        items = []
        total = 0
        for book_id, quantity in quantities.items():
            book = books[book_id]
            items.append(
                OrderItem(
                    order=order,
                    book=book,
                    # Copies: the order keeps the title and price of today
                    title=book.title,
                    price=book.price,
                    quantity=quantity,
                )
            )
            total += book.price * quantity
            # Reserve: the copies are taken from the stock now, not after
            # payment, so nobody else can buy them while this user pays.
            # Returned only if the order is cancelled (cancel_order()).
            stocks[book_id].quantity -= quantity

        # One INSERT for all items, one UPDATE for all stock rows
        OrderItem.objects.bulk_create(items)
        Stock.objects.bulk_update(stocks.values(), ["quantity"])

        order.total = total
        order.save(update_fields=["total", "updated_at"])

        # The email is queued only AFTER COMMIT. Queued right here, inside
        # the transaction, it could promise an order that is then rolled back
        # (an error later in this block, a failed COMMIT), or the worker could
        # take it before the COMMIT and not find the order. on_commit() keeps
        # the function and calls it when the outermost atomic() commits;
        # after a rollback it is simply dropped.
        # A Celery task (worker "celery"): the checkout doesn't wait for
        # Gmail, and a failed email is retried (orders/tasks.py)
        enqueue_on_commit(send_order_created_email_task, order.pk)

    return order


def cancel_order(order_id, *, user=None, only_unpaid=False, notify_customer=False):
    """Cancel an order and return its books to the stock.

    user=None: a manager (admin) or a command — any not cancelled order.
    user=<User>: the customer — only their own order, only while
    Order.can_be_cancelled_by_customer is True.
    only_unpaid=True: the cancel_unpaid_orders command — only a "new" order
    with no payment, checked under the lock: a payment may arrive between
    the command's SELECT and this call.
    notify_customer=True: the customer gets the email "order cancelled"
    (after COMMIT, a Celery task). The cancel_unpaid_orders command: the
    customer didn't cancel it and must learn why the books are gone. Not for
    the customer's own "Cancel" button (they know) and not for a manager in
    the admin (a manager talks to the customer anyway).

    Raises OrderError if the order can't be cancelled.
    """
    with transaction.atomic():
        # Lock the order first: a payment (stage 7 webhook) that arrives at
        # the same moment waits, so "cancelled" and "paid" can't both win.
        # The rules are checked AFTER the lock, on the fresh row.
        order = Order.objects.select_for_update().get(pk=order_id)

        if user is not None:
            if order.user_id != user.pk:
                # Same text as for a missing order: don't reveal that it exists
                raise OrderError(_("Order not found."))
            if not order.can_be_cancelled_by_customer:
                raise OrderError(_("%(order)s can't be cancelled any more.") % {"order": order})
        if order.status == Order.Status.CANCELLED:
            raise OrderError(_("%(order)s is already cancelled.") % {"order": order})
        if only_unpaid and not (
            order.status == Order.Status.NEW and order.payment_status == Order.PaymentStatus.UNPAID
        ):
            raise OrderError(_("%(order)s is not a new unpaid order any more.") % {"order": order})

        # Return the reserved copies to the default warehouse, where
        # create_order() took them. return_to_stock() adds in SQL
        # (UPDATE ... SET quantity = quantity + n), on the current value.
        # The rows are locked by the UPDATE itself; going in book_id order
        # keeps the lock order the same as in create_order().
        warehouse = Warehouse.objects.get_default()
        for item in order.items.order_by("book_id"):
            return_to_stock(item.book_id, item.quantity, warehouse)

        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])

        # An open Stripe page of this order could still be paid after the
        # cancellation: close it. After COMMIT: a request to Stripe is slow
        # and must not run while the order is locked.
        # Imported here: payments.services imports orders.models, a
        # module-level import both ways would be a circular import.
        from payments.services import close_open_payments

        transaction.on_commit(partial(close_open_payments, order.pk))
        if notify_customer:
            enqueue_on_commit(send_order_cancelled_email_task, order.pk)

    return order
