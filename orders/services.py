"""Business logic of orders: create an order from the cart, cancel an order.

Kept out of the views: the same functions are used by the checkout page,
the "Cancel" button, the admin (stage 8) and the cancel_unpaid_orders
command, and the rules (locks, stock) must be the same everywhere.
"""

from decimal import Decimal
from functools import partial

from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from books.models import BookFormat
from config.celery import enqueue_on_commit
from currencies.models import BASE_CURRENCY
from currencies.services import available_currencies, convert, cross_rate, current_rates
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


# A cross rate (UAH -> USD = 0.0220131...) stored in OrderItem.exchange_rate
CROSS_RATE_PLACES = Decimal("0.0000000001")


def create_order(
    user,
    quantities,
    *,
    full_name,
    phone,
    address,
    currency=BASE_CURRENCY,
    idempotency_key="",
):
    """Create an order from {format_id: quantity} and reserve the paper copies.

    A line is a FORMAT of a book (paper, e-book, audiobook) with its own
    price. Only paper books have copies in the warehouse: they are checked
    and reserved; an e-book or an audiobook is a file, always available.
    Every format must be on sale (BookFormat.is_active).

    currency: the code of the order currency (the checkout sends the one of
    the switcher). Every format is converted from its own currency at
    today's rate: the price of one copy is rounded to 0.01, then multiplied
    by the quantity (the same numbers the cart showed). The order keeps the
    rates it used (Order.exchange_rate, OrderItem.exchange_rate), so it
    never changes when the rates do.

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
    1. Lock the stock rows of the ordered paper books (SELECT ... FOR UPDATE).
    2. Check that every format exists, is on sale and (paper) has enough copies.
    3. Create the Order and its OrderItems with the current prices.
    4. Reserve: quantity -= ordered for every stock row.
    5. COMMIT: the locks are released.

    Raises OrderError if the cart is empty or something is missing; the
    database stays unchanged then.
    """
    if not quantities:
        raise OrderError(_("The cart is empty."))
    # One read of the rates for the whole order: every item and the order
    # itself use the same numbers even if a new rate is saved meanwhile
    rates = current_rates()
    if currency not in {offered.code for offered in available_currencies()}:
        raise OrderError(_("Orders in %(currency)s are not accepted.") % {"currency": currency})

    with transaction.atomic():
        warehouse = Warehouse.objects.get_default()

        # The formats with their books, without a lock: OrderItem copies
        # the title, the type and the price
        formats = BookFormat.objects.select_related("book").in_bulk(list(quantities))

        # select_for_update(): other transactions that want to lock or
        # change these rows WAIT until this one ends. Without the lock two
        # users could both read stock = 1 and both buy the last copy:
        #   A: reads stock 1 -> ok        B: reads stock 1 -> ok
        #   A: stock = 0                  B: stock = 0  (2 copies sold, 1 existed)
        # With the lock B waits on its SELECT, then reads stock 0 -> error.
        #
        # The locked rows are the Stock rows (paper format + warehouse), not
        # the books: the stock lives there. Editing a book's title or price
        # at the same moment doesn't wait for a checkout. An e-book has no
        # row and needs no lock.
        #
        # order_by("format_id"): every checkout locks the rows in the same
        # order. Otherwise A could lock format 1 and wait for format 2,
        # while B locked format 2 and waits for format 1 -> deadlock
        # (PostgreSQL would cancel one).
        paper_ids = [pk for pk, book_format in formats.items() if book_format.is_paper]
        stocks = {
            stock.format_id: stock
            for stock in Stock.objects.select_for_update()
            .filter(warehouse=warehouse, format_id__in=paper_ids)
            .order_by("format_id")
        }

        problems = []
        for format_id, quantity in quantities.items():
            book_format = formats.get(format_id)
            if book_format is None:
                problems.append(_("A book from your cart is no longer sold."))
                continue
            title = book_format.book.title
            if not book_format.is_active:
                problems.append(
                    _("“%(title)s” (%(format)s) is not on sale any more.")
                    % {"title": title, "format": book_format.get_format_type_display()}
                )
            elif book_format.currency_id not in rates:
                # Only if the rates of the format's currency were deleted by hand
                problems.append(
                    _("“%(title)s” can't be sold now: no exchange rate for %(currency)s.")
                    % {"title": title, "currency": book_format.currency_id}
                )
            elif book_format.is_paper:
                # No row in the default warehouse = nothing to sell
                available = stocks[format_id].quantity if format_id in stocks else 0
                if available == 0:
                    problems.append(_("“%(title)s” is out of stock.") % {"title": title})
                elif available < quantity:
                    # ngettext: the form depends on the number. Ukrainian
                    # has three ("залишився 1 примірник", "2 примірники",
                    # "5 примірників"), English two; the .po file holds them all
                    problems.append(
                        ngettext(
                            "“%(title)s”: only %(stock)s copy left, you ordered %(quantity)s.",
                            "“%(title)s”: only %(stock)s copies left, you ordered %(quantity)s.",
                            available,
                        )
                        % {"title": title, "stock": available, "quantity": quantity}
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
            currency_id=currency,
            # UAH for 1 unit of the order currency today (1 for UAH)
            exchange_rate=rates[currency].value,
            idempotency_key=idempotency_key,
        )

        items = []
        total = Decimal("0.00")
        for format_id, quantity in quantities.items():
            book_format = formats[format_id]
            # The price of ONE copy in the order currency, rounded
            price = convert(book_format.price, book_format.currency_id, currency, rates)
            items.append(
                OrderItem(
                    order=order,
                    book=book_format.book,
                    format=book_format,
                    # Copies: the order keeps the title, the type and the
                    # price of today
                    format_type=book_format.format_type,
                    title=book_format.book.title,
                    price=price,
                    original_price=book_format.price,
                    original_currency_id=book_format.currency_id,
                    exchange_rate=cross_rate(book_format.currency_id, currency, rates).quantize(
                        CROSS_RATE_PLACES
                    ),
                    quantity=quantity,
                )
            )
            total += price * quantity
            # Reserve: the copies are taken from the stock now, not after
            # payment, so nobody else can buy them while this user pays.
            # Returned only if the order is cancelled (cancel_order()).
            if book_format.is_paper:
                stocks[format_id].quantity -= quantity

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
    """Cancel an order and return its paper books to the stock.

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

        # Return the reserved paper copies to the default warehouse, where
        # create_order() took them; an e-book or an audiobook took none.
        # return_to_stock() adds in SQL (UPDATE ... SET quantity = quantity
        # + n), on the current value. The rows are locked by the UPDATE
        # itself; going in format_id order keeps the lock order the same as
        # in create_order().
        warehouse = Warehouse.objects.get_default()
        paper_items = order.items.filter(format_type=BookFormat.FormatType.PAPER)
        for item in paper_items.order_by("format_id"):
            return_to_stock(item.format_id, item.quantity, warehouse)

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
