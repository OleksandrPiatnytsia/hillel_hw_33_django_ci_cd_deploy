from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from currencies.models import BASE_CURRENCY


class Payment(models.Model):
    """One attempt to pay (part of) an order through one provider.

    An order may have several payments:
    - a Stripe Checkout Session expired -> the user presses "Pay" again ->
      a new Payment, the old one stays as "expired" (history);
    - a manager enters a manual payment for a part of the sum ->
      the order becomes partially_paid.
    Only payments with status "succeeded" count towards the order's
    payment_status (Order.refresh_payment_status(), stage 5).
    """

    class Provider(models.TextChoices):
        STRIPE = "stripe", "Stripe"  # a name, not translated
        # Entered by a manager in the admin: cash, bank transfer, ...
        MANUAL = "manual", _("Manual")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")  # created, waiting for the provider
        SUCCEEDED = "succeeded", _("Succeeded")  # money received
        FAILED = "failed", _("Failed")  # the provider refused
        EXPIRED = "expired", _("Expired")  # the user didn't pay in time

    order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("order"),
        # PROTECT: a payment is a financial record; an order with payments
        # can't be deleted (cancel it instead)
        on_delete=models.PROTECT,
        related_name="payments",  # order.payments.all()
    )
    provider = models.CharField(_("provider"), max_length=20, choices=Provider)
    # Id of the payment on the provider's side, for Stripe the Checkout
    # Session id "cs_test_...". The webhook finds the Payment by it.
    # Empty for manual payments.
    external_id = models.CharField(_("provider's id"), max_length=255, blank=True)
    # In the currency below. For Stripe it's what is still due; a manual
    # payment may be any positive part of it.
    amount = models.DecimalField(
        _("amount"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    # Always the currency of the order (payments.services sets it): the
    # order total, the paid sum and what is due are all in it. Stored in
    # the payment too: Stripe is asked for this currency, and the webhook
    # checks that the money came in it (a wrong currency is not counted).
    # default=UAH: the payments made before currencies existed were in UAH.
    currency = models.ForeignKey(
        "currencies.Currency",
        verbose_name=_("currency"),
        on_delete=models.PROTECT,
        default=BASE_CURRENCY,
        related_name="payments",
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status,
        default=Status.PENDING,
    )
    # Raw data from the provider (e.g. the webhook event) or a manager's
    # note, for debugging and disputes. default=dict: a new empty dict for
    # every payment (default={} would share one dict object).
    details = models.JSONField(_("details"), default=dict, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    # When the money was received; empty until status is "succeeded"
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        constraints = [
            # The same provider id can't be saved twice: Stripe may deliver
            # one webhook several times, and two Payment rows for one
            # Checkout Session would count the money twice.
            # condition: only for non-empty ids, otherwise the second manual
            # payment (external_id = "") would break the rule.
            models.UniqueConstraint(
                fields=["provider", "external_id"],
                condition=~models.Q(external_id=""),
                name="payments_payment_unique_external_id",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="payments_payment_amount_positive",
            ),
        ]

    def __str__(self):
        # Imported here: currencies.display imports the services (cache,
        # rates); a models module imported at startup should not need them
        from currencies.display import format_money

        return gettext("%(provider)s %(amount)s (%(status)s) for order #%(order)s") % {
            "provider": self.get_provider_display(),
            "amount": format_money(self.amount, self.currency_id),
            "status": self.get_status_display(),
            "order": self.order_id,
        }
