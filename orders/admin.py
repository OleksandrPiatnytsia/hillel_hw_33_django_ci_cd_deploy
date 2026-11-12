from decimal import Decimal

from django.contrib import admin, messages
from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from payments.admin import ManualPaymentFormSet, ManualPaymentInline, PaymentInline
from payments.models import Payment
from payments.services import PaymentError, record_manual_payment

from .models import Order, OrderItem
from .services import OrderError, cancel_order

# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------


class OrderItemInline(admin.TabularInline):
    """Books of the order — view only.

    Items are created only at checkout (orders.services.create_order):
    editing them here would change the order without touching the stock
    reserve and the stored total.
    """

    model = OrderItem
    fields = ["book", "title", "price", "quantity", "cost"]
    readonly_fields = fields
    extra = 0

    def get_queryset(self, request):
        # book is shown as a link with its __str__ (title + author)
        return super().get_queryset(request).select_related("book__author")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description=_("cost"))
    def cost(self, obj):
        # An empty (unsaved) row has no price yet
        return obj.cost if obj.pk else ""


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "user",
        "status",
        "payment_status",
        "paid_percent_column",
        "total",
        "created_at",
    ]
    list_filter = ["status", "payment_status", "created_at"]
    # id__exact: "15" finds order #15; a text term is skipped for this field
    # (not an error), so one search box works for numbers and emails
    search_fields = ["id__exact", "user__email", "user__username", "full_name", "phone"]
    date_hierarchy = "created_at"
    list_select_related = ["user"]  # user via JOIN, not a query per row
    ordering = ["-created_at", "-pk"]
    actions = ["cancel_selected"]
    inlines = [OrderItemInline, PaymentInline, ManualPaymentInline]

    readonly_fields = [
        "user",
        "payment_status",
        "total",
        "paid_amount_display",
        "amount_due_display",
        "paid_percent_display",
        "created_at",
        "updated_at",
    ]
    fieldsets = [
        (None, {"fields": ["user", "status"]}),
        (
            _("Payment"),
            {
                "fields": [
                    "payment_status",
                    "total",
                    "paid_amount_display",
                    "amount_due_display",
                    "paid_percent_display",
                ]
            },
        ),
        (_("Delivery"), {"fields": ["full_name", "phone", "address"]}),
        (_("Timestamps"), {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    # Orders are created only at checkout and never deleted (financial
    # records; PROTECT on payments would block it anyway): "Cancel" instead
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.status == Order.Status.CANCELLED:
            # A cancelled order can't come back: its books are already
            # returned to the stock and may be sold to someone else
            readonly.append("status")
        return readonly

    def get_queryset(self, request):
        # Paid sum for the "paid" column in the same SQL query: a subquery
        # per row inside the SELECT, not a separate query per row.
        # Not Sum("payments__amount") + annotate: a JOIN with the payments
        # together with other joins could count rows twice.
        paid = (
            Payment.objects.filter(order=OuterRef("pk"), status=Payment.Status.SUCCEEDED)
            .values("order")  # GROUP BY order
            .annotate(total=Sum("amount"))
            .values("total")
        )
        return (
            super()
            .get_queryset(request)
            .annotate(
                paid_sum=Coalesce(
                    Subquery(paid),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            )
        )

    # ------------------------------------------------------------------
    # Columns and read-only fields
    # ------------------------------------------------------------------

    @admin.display(description=_("paid"), ordering="paid_sum")
    def paid_percent_column(self, obj):
        if obj.total <= 0:
            return "100%"
        return f"{min(int(obj.paid_sum * 100 / obj.total), 100)}%"

    @admin.display(description=_("paid amount"))
    def paid_amount_display(self, obj):
        return gettext("%(amount)s UAH") % {"amount": obj.paid_amount}

    @admin.display(description=_("amount due"))
    def amount_due_display(self, obj):
        return gettext("%(amount)s UAH") % {"amount": obj.amount_due}

    @admin.display(description=_("paid, %"))
    def paid_percent_display(self, obj):
        return f"{obj.paid_percent}%"

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------

    def save_model(self, request, obj, form, change):
        """Save the edited fields; "cancelled" goes through cancel_order().

        Setting the status to "cancelled" by hand would leave the reserved
        books out of the stock, so the change is done by the service, which
        returns them.

        update_fields: only the fields the manager changed. A full save()
        would also write payment_status and total as they were when the page
        was loaded, and could overwrite a payment that came in meanwhile.
        """
        cancel = "status" in form.changed_data and obj.status == Order.Status.CANCELLED
        changed = [name for name in form.changed_data if name != "status" or not cancel]
        if cancel:
            obj.status = form.initial["status"]
        if changed:
            obj.save(update_fields=[*changed, "updated_at"])

        if cancel:
            self._cancel(request, obj)
            obj.refresh_from_db()

    def save_formset(self, request, form, formset, change):
        if not isinstance(formset, ManualPaymentFormSet):
            super().save_formset(request, form, formset, change)
            return
        # New manual payments: through the service, not formset.save().
        # formset.save() would also fill these three lists; the admin reads
        # them for the change history ("Added payment ..."), so they are set
        # here by hand.
        formset.new_objects, formset.changed_objects, formset.deleted_objects = [], [], []
        for payment_form in formset.forms:
            if not payment_form.has_changed():
                continue
            try:
                payment = record_manual_payment(
                    form.instance.pk,
                    payment_form.cleaned_data["amount"],
                    note=payment_form.cleaned_data["note"],
                    recorded_by=request.user,
                )
            except PaymentError as error:
                messages.error(request, str(error))
            else:
                formset.new_objects.append(payment)
                messages.success(
                    request,
                    gettext("Manual payment %(amount)s UAH recorded, the order is %(status)s now.")
                    % {
                        "amount": payment.amount,
                        "status": payment.order.get_payment_status_display().lower(),
                    },
                )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _cancel(self, request, order):
        try:
            cancel_order(order.pk)
        except OrderError as error:
            for text in error.messages:
                messages.error(request, text)
            return False
        messages.success(
            request,
            gettext("%(order)s is cancelled, the books are back in stock.") % {"order": order},
        )
        if order.payment_status != Order.PaymentStatus.UNPAID:
            messages.warning(
                request,
                gettext("%(order)s has payments: return the money to the customer.")
                % {"order": order},
            )
        return True

    @admin.action(
        description=_("Cancel selected orders (books go back to stock)"),
        permissions=["change"],
    )
    def cancel_selected(self, request, queryset):
        for order in queryset:
            self._cancel(request, order)
