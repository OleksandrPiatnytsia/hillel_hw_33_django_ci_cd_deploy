"""Sentry: errors of the site and of the Celery tasks go to sentry.io.

Called once from the end of config/settings/base.py, so it runs in every process
that loads the settings: gunicorn workers (web), the Celery worker and
Celery Beat (config/celery.py loads the settings too).

What gets to Sentry:
- an exception nobody caught in a view -> the user sees templates/500.html,
  Sentry gets the traceback, the URL, the method, the headers (without
  cookies, bodies and personal data, see data_collection);
- an exception in a Celery task after the LAST retry (the retries in between
  are not errors yet: Celery raises Retry, Sentry ignores it);
- logger.error() / logger.exception() anywhere: an event too
  (LoggingIntegration, on by default); INFO and WARNING lines are kept as
  "breadcrumbs": the steps before the error, shown with it;
- a part of the requests and tasks with their timing ("Performance", see
  traces_sampler).

Without SENTRY_DSN nothing is sent and the SDK isn't even started: local
runserver and the tests work as before.
"""

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger

# Requests that are never timed: Docker calls /health/ every 10 seconds
# (web and nginx), 17 000 useless traces a day out of the monthly quota
NOT_TRACED_PATHS = ("/health/",)

# Loggers whose lines carry personal data (the IP address of a login, a
# username + IP of an API token): not sent to Sentry as breadcrumbs.
PRIVATE_LOGGERS = ("users.signals", "api.views")


def request_path(sampling_context):
    """The path of the HTTP request being sampled, or None for a Celery task.

    Under ASGI (gunicorn + uvicorn in Docker) the SDK gives the ASGI scope,
    under WSGI (runserver) the WSGI environ.
    """
    if scope := sampling_context.get("asgi_scope"):
        return scope.get("path")
    if environ := sampling_context.get("wsgi_environ"):
        return environ.get("PATH_INFO")
    return None


def make_traces_sampler(rate):
    """Which part of the requests / tasks is timed: a number from 0 to 1.

    rate = SENTRY_TRACES_SAMPLE_RATE: 0.1 = every tenth request.
    """

    def traces_sampler(sampling_context):
        # A task queued by a timed request: follow that decision, so the
        # trace in Sentry is whole (the request + its email task) or absent
        if sampling_context.get("parent_sampled") is not None:
            return float(sampling_context["parent_sampled"])
        if request_path(sampling_context) in NOT_TRACED_PATHS:
            return 0.0
        return rate

    return traces_sampler


def before_breadcrumb(crumb, hint):
    """Drop the log lines with personal data (None = don't keep it)."""
    if crumb.get("category") in PRIVATE_LOGGERS:
        return None
    return crumb


def init_sentry(dsn, *, environment=None, traces_sample_rate=0.0, **options):
    """Start the Sentry SDK. Returns False (and does nothing) without a DSN.

    options: extra arguments of sentry_sdk.init (the tests pass a transport
    that keeps the events in memory instead of sending them).
    """
    if not dsn:
        return False

    sentry_sdk.init(
        # The address of the project in Sentry, with its public key:
        # Settings -> Projects -> <project> -> Client Keys (DSN)
        dsn=dsn,
        # "docker" / "local" / "production": a filter in Sentry. Unset ->
        # the SDK uses "production", and errors of a laptop would look like
        # errors of the real site.
        environment=environment,
        # Django: exceptions of views, the request in the event, timing of
        # the views, templates, SQL queries and cache calls.
        # Celery: exceptions of tasks, timing of tasks; propagate_traces
        # links a task to the request that queued it.
        # (Both would be found by the SDK anyway; listed to be explicit.)
        integrations=[DjangoIntegration(), CeleryIntegration(propagate_traces=True)],
        # What is collected with an event. Sentry keeps the events on its
        # servers: no personal data there, and nothing that lets anyone log in.
        # (data_collection replaces send_default_pii, deprecated in 2.74.)
        data_collection={
            # No user id / email / IP address in the event
            "user_info": False,
            # No cookies at all: sessionid would let anyone log in as the user
            "cookies": {"mode": "off"},
            # Headers yes (User-Agent, Accept-Language, ...), except the ones
            # with the client address. Authorization (the JWT), X-CSRFToken
            # and other secrets are always "[Filtered]" by the SDK itself.
            "http_headers": {
                "request": {"mode": "denylist", "terms": ["forwarded", "-ip", "remote-", "via"]},
            },
            # No request bodies: checkout forms have names, phones, addresses
            "http_bodies": [],
            # No values of SQL parameters (emails, phones) in the SQL timings
            "database_query_data": False,
        },
        traces_sampler=make_traces_sampler(traces_sample_rate),
        before_breadcrumb=before_breadcrumb,
        **options,
    )

    # Bots knock with a made-up Host header ("Invalid HTTP_HOST header",
    # logged as ERROR by Django). Not a bug of ours, just noise in Sentry.
    ignore_logger("django.security.DisallowedHost")

    # No log line here: this runs inside base.py, before Django sets up
    # LOGGING, so a logger.info() would go nowhere. To check that Sentry is
    # on: sentry_sdk.get_client().is_active() (see README).
    return True
