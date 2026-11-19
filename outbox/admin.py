"""The outbox in the admin: what was sent to Analytics, what waits and why.

View only: a row is the record of an event as it happened, editing it would
send Analytics something that never happened. The only action: "Send now".
"""

from django.contrib import admin, messages
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from .models import OutboxEvent
from .tasks import publish_pending_events


class PublishedFilter(admin.SimpleListFilter):
    title = _("sent")
    parameter_name = "sent"

    def lookups(self, request, model_admin):
        return [("yes", _("Yes")), ("no", _("No, waiting"))]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(published_at__isnull=False)
        if self.value() == "no":
            return queryset.filter(published_at__isnull=True)
        return queryset


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = [
        "type",
        "order_id",
        "is_sent",
        "created_at",
        "published_at",
        "failed_attempts",
        "event_id",
    ]
    list_filter = [PublishedFilter, "type", "created_at"]
    # A number: the search box finds the events of one order
    search_fields = ["=order_id", "=event_id"]
    date_hierarchy = "created_at"
    actions = ["publish_now"]
    fields = [
        "event_id",
        "type",
        "order_id",
        "created_at",
        "published_at",
        "failed_attempts",
        "last_error",
        "payload",
    ]
    readonly_fields = fields

    @admin.display(description=_("sent"), boolean=True, ordering="published_at")
    def is_sent(self, event):
        # A green tick / a red cross: clearer than an empty "published at"
        return event.published_at is not None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # The page opens (view permission), nothing can be saved
        return False

    def has_delete_permission(self, request, obj=None):
        # An unsent event deleted by hand never reaches Analytics; the sent
        # ones are deleted by the nightly task (outbox.tasks.delete_old_events)
        return False

    @admin.action(description=_("Send the waiting events now"))
    def publish_now(self, request, queryset):
        # All waiting events, not only the selected ones: they go in order,
        # a selected later event must not overtake an earlier one
        sent = publish_pending_events()
        waiting = OutboxEvent.objects.filter(published_at__isnull=True).count()
        level = messages.WARNING if waiting else messages.SUCCESS
        self.message_user(
            request,
            gettext("Sent: %(sent)s, still waiting: %(waiting)s.")
            % {"sent": sent, "waiting": waiting},
            level,
        )
