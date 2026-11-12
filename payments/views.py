from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from orders.models import Order

from .models import Payment
from .providers.base import PaymentProviderError
from .providers.registry import get_provider
from .services import PaymentError, start_online_payment, sync_payment


@login_required
@require_POST
def pay(request, order_id):
    """The "Pay" button: redirect to the provider's payment page."""
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    try:
        url = start_online_payment(order.pk, request.user, request)
    except PaymentError as error:
        messages.error(request, str(error))
        return redirect(order)
    # A redirect to another site (checkout.stripe.com): fine here, the URL
    # comes from Stripe's answer, not from the request
    return redirect(url)


@login_required
def payment_success(request):
    """Stripe redirects here after the payment: ?session_id=cs_test_...

    The session id in the URL is NOT a proof of payment (anyone can type
    the address). It only tells which payment to check; the status comes
    from Stripe itself (sync_payment -> sessions.retrieve with our secret key).
    """
    payment = get_object_or_404(
        Payment.objects.select_related("order"),
        external_id=request.GET.get("session_id", ""),
        order__user=request.user,
    )
    payment = sync_payment(payment)
    return render(
        request, "payments/payment_success.html", {"payment": payment, "order": payment.order}
    )


@login_required
def payment_cancelled(request, payment_id):
    """Stripe's "back" link: nothing is paid, the order stays as it was.

    The payment page stays open until it expires: "Pay" again reuses it.
    """
    payment = get_object_or_404(Payment, pk=payment_id, order__user=request.user)
    messages.info(
        request,
        _("The payment was not completed. You can pay later with the “Pay” button."),
    )
    return redirect("orders:detail", pk=payment.order_id)


# csrf_exempt: the request comes from Stripe, not from our form, so it has
# no CSRF token. Its authenticity is checked by the provider instead
# (Stripe: the signature header). No login: Stripe is not a user.
@csrf_exempt
@require_POST
def webhook(request, provider_name):
    """POST /payments/webhook/<provider>/ -> provider.handle_webhook()."""
    try:
        provider = get_provider(provider_name)
        return provider.handle_webhook(request)
    except PaymentProviderError:
        # Unknown provider, or one without webhooks (manual)
        raise Http404 from None
