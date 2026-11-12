"""The "Tools" block of the profile page: links to every service page of the
project in one place. Only for a superuser (users/templates/users/profile.html).

Internal pages are built with reverse(): a changed URL can't leave a dead
link. External services (Flower, Sentry, Stripe) come from the settings:
a service that isn't set up (no SENTRY_ISSUES_URL, no Stripe key) has no link.
"""

from dataclasses import dataclass

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Tool:
    title: str
    url: str
    description: str
    # Another site / port: opened in a new tab, with "↗" next to the name
    external: bool = False


def stripe_dashboard_url():
    """The payments in the Stripe dashboard: test or live, as the key is."""
    key = settings.STRIPE_SECRET_KEY
    if not key:
        return None
    test = "test/" if key.startswith("sk_test_") else ""
    return f"https://dashboard.stripe.com/{test}payments"


def admin_tools():
    """[(group title, [Tool, ...]), ...] in the order they are shown."""
    site = [
        Tool(_("Admin"), reverse("admin:index"), _("Books, authors, users, groups")),
        Tool(
            _("Orders"),
            reverse("admin:orders_order_changelist"),
            _("Statuses, cancellation, payments"),
        ),
        Tool(
            _("Stock"),
            reverse("admin:inventory_stock_changelist"),
            _("Copies of every book in the warehouse"),
        ),
    ]
    api = [
        Tool(_("Browsable API"), reverse("api:api-root"), _("The API in the browser, with forms")),
        Tool("Swagger", reverse("api:docs"), _("API documentation, requests right from the page")),
        Tool("ReDoc", reverse("api:redoc"), _("API documentation for reading")),
        Tool(_("OpenAPI schema"), reverse("api:schema"), _("For Postman and client generators")),
    ]
    monitoring = [
        Tool(_("Health check"), reverse("health"), _("PostgreSQL and Redis answer (JSON)")),
        Tool("Flower", settings.FLOWER_URL, _("Celery tasks and workers, live"), external=True),
    ]
    if settings.SENTRY_ISSUES_URL:
        monitoring.append(
            Tool(
                "Sentry",
                settings.SENTRY_ISSUES_URL,
                _("Errors of the site and of the tasks"),
                external=True,
            )
        )
    monitoring.append(
        Tool(
            _("Sentry test error"),
            reverse("sentry_debug"),
            _("Raises an error on purpose: check that Sentry gets it"),
        )
    )
    groups = [(_("Site"), site), ("API", api), (_("Monitoring"), monitoring)]

    if stripe_url := stripe_dashboard_url():
        groups.append(
            (_("Payments"), [Tool("Stripe", stripe_url, _("Payments and webhooks"), external=True)])
        )
    return groups
