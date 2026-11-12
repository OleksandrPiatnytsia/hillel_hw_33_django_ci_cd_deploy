from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from decimal import Decimal

from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.formats import number_format
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.generic import ListView

from books.views import ElidedPaginationMixin
from cart.cart import Cart

from .forms import CheckoutForm
from .models import Order
from .services import OrderError, cancel_order, create_order


@login_required  # anonymous -> LOGIN_URL?next=/orders/checkout/; the cart stays
# PUT / DELETE / PATCH -> 405 (they used to get the form page with 200)
@require_http_methods(["GET", "POST"])
def checkout(request):
    """Delivery form + cart summary; POST creates the order.

    GET  -> the form, prefilled from the profile.
    POST -> valid form -> create_order() (one transaction) -> clear the cart
            -> the order page with the "Pay" button. A stock problem -> back
            to the cart with the messages, nothing is saved.
    """
    cart = Cart(request)
    if not cart:
        messages.info(request, _("Your cart is empty."))
        return redirect("cart:detail")

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            try:
                data = form.cleaned_data
                order = create_order(
                    request.user,
                    cart.quantities(),
                    full_name=data["full_name"],
                    phone=data["phone"],
                    address=data["address"],
                )
            except OrderError as error:
                for text in error.messages:
                    messages.error(request, text)
                # The cart page shows the current stock next to each book
                return redirect("cart:detail")

            # Only after a successful COMMIT: if create_order() failed,
            # the cart stays for the next attempt
            cart.clear()
            if data["save_to_profile"]:
                # The next checkout is prefilled with these. The name is not
                # saved: "full name" can't be split into first / last name
                # reliably; it's edited on the profile page.
                request.user.phone = data["phone"]
                request.user.address = data["address"]
                request.user.save(update_fields=["phone", "address"])
            messages.success(
                request,
                _(
                    "%(order)s is created, the books are reserved for you. "
                    "Pay for it with the “Pay” button."
                )
                % {"order": order},
            )
            # To the order page, not straight to Stripe: the customer sees the
            # created order first and pays with the "Pay" button
            # (payments.views.pay) — now or later from "My orders".
            return redirect(order)  # Order.get_absolute_url()
    else:
        # Prefilled from the profile (users.User): first + last name, phone,
        # address. Empty for a new user; the checkbox then saves them.
        form = CheckoutForm(
            initial={
                "full_name": request.user.get_full_name(),
                "phone": request.user.phone,
                "address": request.user.address,
            }
        )

    return render(request, "orders/checkout.html", {"form": form})


class OrderListView(LoginRequiredMixin, ElidedPaginationMixin, ListView):
    """My orders: only the current user's, newest first (Order.Meta.ordering).

    Template: orders/order_list.html
    """

    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user).annotate(
                # Copies in the order (2 + 1 = 3), calculated by the database
                # in the same query: GROUP BY order + SUM, not one query per row
                books_count=Sum("items__quantity")
            )
            # Explicit: Django drops Meta.ordering from queries with GROUP BY
            # (aggregation), the list would come in any order. "-pk": a stable
            # order for equal dates, so pages don't repeat or skip orders.
            .order_by("-created_at", "-pk")
        )


@login_required
def order_detail(request, pk):
    """GET /orders/<pk>/ -> one order of the current user.

    Items, delivery data, both statuses, the paid sum and the "Pay" /
    "Cancel" buttons (template orders/order_detail.html). The page checkout
    redirects to after the order is created.
    """
    # user=request.user: someone else's order -> 404, the same as a missing
    # one (403 would tell that order #pk exists)
    order = get_object_or_404(
        Order.objects.prefetch_related("items__book"), pk=pk, user=request.user
    )
    return render(request, "orders/order_detail.html", {"order": order})


@login_required
@require_POST
def order_cancel(request, pk):
    """POST /orders/<pk>/cancel/ -> the customer cancels their order.

    Allowed only for a new unpaid order (Order.can_be_cancelled_by_customer);
    the books go back to the stock and an open Stripe page is closed
    (orders.services.cancel_order). Success or the reason why not -> a
    message, then back to the order page.
    """
    # Someone else's or a missing order -> 404, like order_detail.
    # cancel_order() checks the owner again under the lock; this is for
    # the right answer to the user.
    get_object_or_404(Order, pk=pk, user=request.user)
    try:
        order = cancel_order(pk, user=request.user)
    except OrderError as error:
        for text in error.messages:
            messages.error(request, text)
    else:
        messages.success(
            request, _("%(order)s is cancelled. The books are back in stock.") % {"order": order}
        )
    return redirect("orders:detail", pk=pk)


@never_cache  # a fresh answer for every poll, never from a browser cache
@require_GET
async def order_status(request, pk):
    """GET /orders/<pk>/status/ -> JSON with the current statuses of the order.

    Polled every few seconds by the "The payment is being confirmed" page
    (payments/payment_success.html + static/js/payment_status.js): when the
    Stripe webhook marks the payment, the page goes to the order by itself.

    Async view with async database queries:
    - await request.auser(): the user (request.user would make a sync query);
    - .afirst(): the order and SUM of its succeeded payments, only the
      needed columns (values()), in one query.
    JSON answers for errors (401 / 404), not redirects or HTML pages: the
    caller is JavaScript, not a person.
    """
    # Imported here: payments.models imports orders.models (see Order.paid_amount)
    from payments.models import Payment

    user = await request.auser()
    if not user.is_authenticated:
        return JsonResponse({"error": "login required"}, status=401)

    # One SQL query: the order and the sum of its succeeded payments
    # (LEFT JOIN payments + GROUP BY order + SUM ... FILTER (WHERE ...)).
    # user=user: someone else's order looks the same as a missing one.
    order = await (
        Order.objects.filter(pk=pk, user=user)
        .annotate(
            paid=Sum(
                "payments__amount",
                filter=Q(payments__status=Payment.Status.SUCCEEDED),
            )
        )
        .values("pk", "status", "payment_status", "total", "paid")
        .afirst()
    )
    if order is None:
        return JsonResponse({"error": "not found"}, status=404)

    # SUM over no rows is NULL in SQL -> None in Python
    paid_amount = order["paid"] or Decimal("0.00")
    amount_due = max(order["total"] - paid_amount, Decimal("0.00"))

    return JsonResponse(
        {
            "id": order["pk"],
            "status": order["status"],
            # The labels in the language of the request ("Оплачено" / "Paid")
            "status_display": str(Order.Status(order["status"]).label),
            "payment_status": order["payment_status"],
            "payment_status_display": str(Order.PaymentStatus(order["payment_status"]).label),
            # Strings formatted for the language ("250,00" / "250.00"):
            # only for showing; the codes above are for the logic
            "paid_amount": number_format(paid_amount, 2),
            "amount_due": number_format(amount_due, 2),
        }
    )
