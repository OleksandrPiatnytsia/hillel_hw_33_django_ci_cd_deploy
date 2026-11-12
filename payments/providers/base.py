from dataclasses import dataclass

from django.utils.translation import gettext as _


class PaymentProviderError(Exception):
    """The provider can't do the operation; the text can be shown to the user."""


@dataclass
class ProviderSession:
    """What start() returns: the provider's id of the payment and where to pay."""

    external_id: str  # saved to Payment.external_id (Stripe: "cs_test_...")
    url: str  # the provider's payment page; the customer is redirected there
    expires_at: int  # Unix time; after it the page doesn't accept payment


class PaymentProvider:
    """What the rest of the project expects from a payment provider.

    Views and services call only these methods and never import Stripe
    (or any other SDK) directly. A new provider = a new subclass + one line
    in registry.py; the checkout, the "Pay" button and the webhook URL stay
    the same.

    The flow of an online provider (Stripe):
        1. "Pay" -> payments.services creates Payment(status=pending)
        2. start(payment, request) -> ProviderSession; the customer is
           redirected to session.url and pays there
        3. the provider tells us the result:
           - the customer comes back -> fetch_status(payment)
           - the provider calls /payments/webhook/<name>/ (stage 7) ->
             handle_webhook(request)
           -> payments.services marks the Payment succeeded / expired
           -> Order.refresh_payment_status()
    """

    # Same value as Payment.Provider ("stripe", "manual"): the registry key,
    # Payment.provider and the <name> part of the webhook URL
    name = ""

    # Can a customer choose it with the "Pay" button? (manual: no)
    customer_facing = False

    def start(self, payment, request):
        """Begin paying `payment` at the provider; return a ProviderSession.

        Raises PaymentProviderError if the provider refuses or is unreachable.
        """
        raise PaymentProviderError(
            _("%(provider)s: online payment is not supported.") % {"provider": self.name}
        )

    def fetch_status(self, payment):
        """Ask the provider about the payment; return a Payment.Status value.

        "succeeded" / "expired" / "failed", or "pending" while it's not decided.
        Raises PaymentProviderError if the provider is unreachable.
        """
        return payment.status

    def cancel(self, payment):
        """Close the payment page so it can't be paid any more.

        Returns True if it was closed, False if it's too late (already paid).
        Default: nothing to close.
        """
        return True

    def handle_webhook(self, request):
        """Process a notification from the provider; return an HttpResponse.

        Must check that the request really comes from the provider
        (signature) before trusting its data.
        """
        raise PaymentProviderError(
            _("%(provider)s: webhooks are not supported.") % {"provider": self.name}
        )
