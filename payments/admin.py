from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from .models import Payment

# ---------------------------------------------------------------------------
# Inlines for the Order page (used by orders/admin.py)
# ---------------------------------------------------------------------------


class PaymentInline(admin.TabularInline):
    """All payments of the order — view only.

    A payment is a financial record: it is changed only by
    payments.services (Stripe webhook, record_manual_payment), never by
    editing a row by hand, which would skip refresh_payment_status().
    """

    model = Payment
    fields = ["created_at", "provider", "amount", "status", "paid_at", "external_id", "note"]
    readonly_fields = fields
    extra = 0
    verbose_name_plural = _("payments")

    # No add / change / delete -> Django shows the rows as plain text
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description=_("note"))
    def note(self, obj):
        return obj.details.get("note", "")


class ManualPaymentForm(forms.ModelForm):
    """One new manual payment: amount + a note (stored in Payment.details)."""

    note = forms.CharField(
        label=_("note"),
        required=False,
        max_length=255,
        help_text=_("cash on delivery, bank transfer #…"),
    )

    class Meta:
        model = Payment
        fields = ["amount"]


class ManualPaymentFormSet(BaseInlineFormSet):
    """Checks the new manual payments together, before anything is saved."""

    def clean(self):
        super().clean()
        order = self.instance  # the Order of the page
        amounts = [
            form.cleaned_data["amount"]
            for form in self.forms
            if form.has_changed() and form.cleaned_data.get("amount")
        ]
        if not amounts:
            return
        if order.status == order.Status.CANCELLED:
            raise ValidationError(gettext("The order is cancelled, payments can't be added."))
        due = order.amount_due
        if sum(amounts) > due:
            raise ValidationError(
                gettext("Only %(due)s UAH is due, the new payments add up to %(sum)s UAH.")
                % {"due": due, "sum": sum(amounts)}
            )


class ManualPaymentInline(admin.TabularInline):
    """ "Add a manual payment" rows under the payments list.

    Shows no existing rows (get_queryset -> none()), only new ones. The rows
    are NOT saved by the admin: OrderAdmin.save_formset() passes each one to
    payments.services.record_manual_payment(), which locks the order,
    checks the amount again and refreshes payment_status.
    """

    model = Payment
    form = ManualPaymentForm
    formset = ManualPaymentFormSet
    fields = ["amount", "note"]
    extra = 0
    can_delete = False
    verbose_name = _("manual payment")
    verbose_name_plural = _("add a manual payment (money received outside the site)")

    def get_queryset(self, request):
        return super().get_queryset(request).none()

    def has_add_permission(self, request, obj=None):
        # Only on an existing, not cancelled order with something left to pay
        return (
            obj is not None
            and obj.status != obj.Status.CANCELLED
            and obj.amount_due > 0
            and super().has_add_permission(request, obj)
        )


# ---------------------------------------------------------------------------
# Payments list
# ---------------------------------------------------------------------------


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """All payments of all orders: search and filters, view only.

    Manual payments are added on the Order page (ManualPaymentInline).
    """

    list_display = ["__str__", "order", "provider", "amount", "status", "paid_at", "created_at"]
    list_filter = ["provider", "status", "created_at"]
    # id__exact: a non-number search term is skipped, not an error
    search_fields = ["external_id", "order__id__exact", "order__user__email"]
    list_select_related = ["order"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
