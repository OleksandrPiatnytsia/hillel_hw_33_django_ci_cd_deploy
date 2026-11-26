"""Permission classes of the API.

A permission class answers "may this request go on?":
    has_permission(request, view)            before the view, for every request
    has_object_permission(request, view, obj) for one object (retrieve,
                                              update, delete), after get_object()
False -> 401 for an anonymous user (with a token or a session the request could
pass), 403 for a logged-in one.

Several classes in permission_classes = ALL of them must allow.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsOwnerOrReadOnly(BasePermission):
    """Read for everybody who got the object; change only for its owner.

    An object-level permission: DRF calls has_object_permission() after
    get_object() found the object (retrieve, update, delete, our "cancel"
    action), not for lists.

    Orders: the queryset of OrderViewSet already decides WHAT a user may
    see (a customer: own orders, someone else's -> 404; staff: all). This
    class decides who may CHANGE an order: only its owner. A manager reads
    every order, but cancels a customer's order in the admin, where the
    rules of a manager apply (refund, the shipped state), not here: 403.

    The model needs a "user" field (the owner).
    """

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.user_id == request.user.pk


class CanExportOrdersForAnalytics(BasePermission):
    """orders.export_orders_for_analytics: the account of Analytics (group Services).

    Its own permission, not is_staff: the service reads the orders for the
    backfill and can do nothing else. Not logged in -> 401, another
    account (a customer, a manager) -> 403.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and user.has_perm("orders.export_orders_for_analytics")
        )
