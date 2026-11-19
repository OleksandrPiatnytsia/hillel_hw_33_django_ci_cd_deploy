from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from books.models import BookFormat
from currencies.models import BASE_CURRENCY


class Order(models.Model):
    """An order of one user: delivery data, two statuses and the total.

    Two independent statuses:
    - status: what happens to the goods (fulfilment), changed by managers;
    - payment_status: how much is paid, calculated from the payments
      (payments.Payment), never set by hand.
    An order may be shipped before it is fully paid (manual payment on
    delivery) or paid and then cancelled, so one field can't hold both.
    """

    class Status(models.TextChoices):
        # TextChoices: the first value is stored in the database, the second
        # is the label for forms and the admin (order.get_status_display())
        # The labels are lazy: get_status_display() shows them in the
        # language of the request. The stored values ("new") never change.
        NEW = "new", _("New")
        PROCESSING = "processing", _("Processing")
        SHIPPED = "shipped", _("Shipped")
        COMPLETED = "completed", _("Completed")
        CANCELLED = "cancelled", _("Cancelled")

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", _("Unpaid")
        PARTIALLY_PAID = "partially_paid", _("Partially paid")
        PAID = "paid", _("Paid")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        # PROTECT: an order is a financial record, it must outlive any
        # attempt to delete its user (deactivate the user instead)
        on_delete=models.PROTECT,
        related_name="orders",  # user.orders.all() -> "My orders"
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status,
        default=Status.NEW,
    )
    # Stored (not calculated on every read) so the admin can filter by it.
    # Only Order.refresh_payment_status() (stage 5) changes it, from the sum
    # of succeeded payments: 0 -> unpaid, less than total -> partially_paid,
    # total or more -> paid.
    payment_status = models.CharField(
        _("payment status"),
        max_length=20,
        choices=PaymentStatus,
        default=PaymentStatus.UNPAID,
    )

    # Delivery data from the checkout form. A copy, not a link to the user's
    # profile: a later profile change must not change an old order.
    full_name = models.CharField(_("full name"), max_length=255)
    phone = models.CharField(_("phone"), max_length=30)
    address = models.TextField(_("delivery address"))

    # The currency of the order: chosen at checkout (the currency of the
    # switcher), never changed afterwards. The prices of the items, the
    # total and the payments are in it.
    # default=UAH: the orders made before currencies existed were in UAH
    # (the migration fills them), and so is an order of the API without
    # a currency.
    currency = models.ForeignKey(
        "currencies.Currency",
        verbose_name=_("currency"),
        on_delete=models.PROTECT,
        default=BASE_CURRENCY,
        related_name="orders",
    )
    # How many UAH for 1 unit of the order currency on the day of the order
    # (1 for UAH). Reports add up orders of different currencies in UAH with
    # it: the revenue of an order stays the same when the rates change later.
    exchange_rate = models.DecimalField(
        _("exchange rate"),
        max_digits=12,
        decimal_places=6,
        default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0.000001"))],
        help_text=_("UAH for 1 unit of the order currency on the day of the order"),
    )

    # Sum of the items (price * quantity), in the order currency. Stored:
    # the price of a book may change later, the order must keep the sum the
    # user agreed to pay.
    total = models.DecimalField(
        _("total"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    # The Idempotency-Key header of POST /api/orders/: a client that sends
    # the same request again (no answer because of a timeout, a retry)
    # gets the order made by the first one instead of a second order.
    # Unique per user (see Meta.constraints); "" = no key (the site, an
    # API request without the header). editable=False: not in admin forms.
    idempotency_key = models.CharField(
        _("idempotency key"), max_length=255, blank=True, default="", editable=False
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["-created_at"]  # newest first
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        constraints = [
            # Validators run only in forms (full_clean); the constraint also
            # protects against code and SQL that skip them
            models.CheckConstraint(
                condition=models.Q(total__gte=0),
                name="orders_order_total_not_negative",
            ),
            # One order per key of a user. In the database, not only a check
            # in the code: two requests with the same key at the same moment
            # both pass a check "is there an order with this key?", but only
            # one INSERT passes the unique index, the other one gets an
            # IntegrityError (api.views.orders handles it).
            # condition: orders without a key ("") are not limited.
            models.UniqueConstraint(
                fields=["user", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="orders_order_unique_idempotency_key_per_user",
            ),
        ]

    def __str__(self):
        # gettext (not lazy): str(order) is built right now, in the active
        # language: "Замовлення #5" / "Order #5" in messages and emails
        return gettext("Order #%(number)s") % {"number": self.pk}

    @property
    def total_uah(self):
        """The total in UAH at the rate of the day of the order (for reports)."""
        return (self.total * self.exchange_rate).quantize(Decimal("0.01"))

    def get_absolute_url(self):
        return reverse("orders:detail", kwargs={"pk": self.pk})

    @property
    def can_be_cancelled_by_customer(self):
        """The customer may cancel only a new order that nobody paid for yet.

        Later (processing, shipped) or after any payment only a manager can
        cancel it (admin, stage 8): goods may be packed, money must be returned.
        """
        return self.status == self.Status.NEW and self.payment_status == self.PaymentStatus.UNPAID

    # ------------------------------------------------------------------
    # Payments (payments.Payment, related_name="payments")
    # ------------------------------------------------------------------

    @property
    def paid_amount(self):
        """Sum of the succeeded payments, in the order currency. One SQL query (SUM)."""
        # Imported here: payments.models points to orders by the string
        # "orders.Order", orders.models doesn't import payments at the top,
        # so the two apps don't import each other at load time
        from payments.models import Payment

        result = self.payments.filter(status=Payment.Status.SUCCEEDED).aggregate(
            total=models.Sum("amount")
        )
        # SUM over no rows is NULL in SQL -> None in Python
        return result["total"] or Decimal("0.00")

    @property
    def amount_due(self):
        """How much is still to pay: total - paid, never below 0."""
        return max(self.total - self.paid_amount, Decimal("0.00"))

    @property
    def paid_percent(self):
        """0..100, whole percent; for display only, not stored.

        Calculated from the stored total and the payments every time, so it
        can't get out of sync with them (a stored percent could).
        """
        if self.total <= 0:
            return 100
        return min(int(self.paid_amount * 100 / self.total), 100)

    def refresh_payment_status(self):
        """Recalculate payment_status from the succeeded payments and save it.

        The ONLY place that changes payment_status:
            0             -> unpaid
            < total       -> partially_paid
            >= total      -> paid
        Called by payments.services after every payment change. The caller
        must hold the lock on this order (select_for_update) inside a
        transaction, so two payments finishing at the same moment can't
        both read the old sum and overwrite each other's result.

        Returns True if the status changed.
        """
        paid = self.paid_amount
        if paid <= 0:
            new_status = self.PaymentStatus.UNPAID
        elif paid < self.total:
            new_status = self.PaymentStatus.PARTIALLY_PAID
        else:
            new_status = self.PaymentStatus.PAID

        if new_status == self.payment_status:
            return False
        self.payment_status = new_status
        self.save(update_fields=["payment_status", "updated_at"])
        if new_status == self.PaymentStatus.PAID:
            # The event for Analytics, in the caller's transaction (the
            # payment services). Only "paid": the contract has no event for
            # a part payment, the next snapshot carries payment_status anyway.
            # Imported here: outbox reads the orders (snapshot), a top-level
            # import both ways would be circular
            from outbox.models import OutboxEvent
            from outbox.services import record_event

            record_event(self, OutboxEvent.Type.ORDER_PAID)
        return True


class OrderItem(models.Model):
    """One line of an order: which book in which format, at what price, how many."""

    order = models.ForeignKey(
        Order,
        verbose_name=_("order"),
        # CASCADE: an item has no meaning without its order
        on_delete=models.CASCADE,
        related_name="items",  # order.items.all()
    )
    book = models.ForeignKey(
        "books.Book",
        verbose_name=_("book"),
        # PROTECT: a book that was ever ordered can't be deleted
        # (set stock to 0 instead), the order history stays complete
        on_delete=models.PROTECT,
        related_name="order_items",  # book.order_items.all()
    )
    # The format that was bought: paper, e-book or audiobook. book is
    # always format.book; kept as its own column for the reports and the
    # "Most popular" sort, which count by book.
    format = models.ForeignKey(
        "books.BookFormat",
        verbose_name=_("format"),
        # PROTECT: a format that was ever ordered can't be deleted (turn
        # off "on sale" instead), like the book
        on_delete=models.PROTECT,
        related_name="order_items",  # book_format.order_items.all()
    )
    # A copy of format.format_type at the moment of ordering: what the
    # customer bought stays the same even if the format is changed later.
    # Cancelling returns copies to the stock only for "paper".
    format_type = models.CharField(
        _("format type"), max_length=10, choices=BookFormat.FormatType.choices
    )
    # Copies of the book data at the moment of ordering: if the title or the
    # price of the book changes later, the old order still shows what was
    # actually bought and for how much
    title = models.CharField(_("title"), max_length=255)
    # The price of one copy in the ORDER currency: the book's price converted
    # at the rate of the day of the order, rounded to 0.01. cost and the
    # order total are calculated from it.
    price = models.DecimalField(
        _("price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    # The price of the format in ITS currency at the moment of ordering
    # (BookFormat.price, BookFormat.currency): 650.00 UAH -> price 14.31 in a USD order.
    # The same as price + order currency when nothing was converted.
    original_price = models.DecimalField(
        _("original price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    original_currency = models.ForeignKey(
        "currencies.Currency",
        verbose_name=_("original currency"),
        on_delete=models.PROTECT,
        related_name="+",  # no currency.orderitem_set: nobody needs it
    )
    # original_price * exchange_rate = price (before rounding): how many
    # units of the order currency for 1 unit of the book's currency. Not
    # rounded to 6 places like the NBU rates: a cross rate UAH -> USD is
    # 0.022013..., 10 places keep it exact enough for any price.
    exchange_rate = models.DecimalField(
        _("exchange rate"),
        max_digits=20,
        decimal_places=10,
        validators=[MinValueValidator(Decimal("0.0000000001"))],
    )
    quantity = models.PositiveIntegerField(
        _("quantity"),
        # PositiveIntegerField allows 0; an item with 0 books makes no sense
        validators=[MinValueValidator(1)],
    )

    class Meta:
        verbose_name = _("order item")
        verbose_name_plural = _("order items")
        constraints = [
            # One line per format in an order: 3 paper books = quantity 3,
            # not 3 lines. The same book in two formats = two lines.
            models.UniqueConstraint(
                fields=["order", "format"],
                name="orders_orderitem_unique_format_per_order",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="orders_orderitem_quantity_at_least_1",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="orders_orderitem_price_not_negative",
            ),
        ]

    def __str__(self):
        return f"{self.display_title} × {self.quantity}"

    @property
    def display_title(self):
        """ "Кобзар (Paper)": the title with the format, in the active language.

        Built when it is read, so an email rendered inside
        translation.override(<the customer's language>) gets the label in
        that language.
        """
        return f"{self.title} ({self.get_format_type_display()})"

    @property
    def cost(self):
        """Price of the whole line: price * quantity."""
        return self.price * self.quantity
