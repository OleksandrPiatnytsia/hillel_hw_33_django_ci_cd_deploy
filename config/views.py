"""Project-level views that don't belong to the books or users apps."""

import asyncio
import logging
import uuid

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.conf import settings
from django.http import Http404, JsonResponse
from django.utils.cache import patch_cache_control
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_safe
from django.views.i18n import set_language as django_set_language
from django.views.static import serve

from .i18n import is_supported_language

logger = logging.getLogger(__name__)  # "config.views"


async def check_database():
    """One small query through the async ORM: proves PostgreSQL answers.

    aexists(): SELECT 1 ... LIMIT 1 on django_content_type, a table every
    Django project has (filled by migrate). The result doesn't matter, only
    that the query ran without an error.
    """
    await ContentType.objects.aexists()


async def check_cache():
    """Write a value to the cache (Redis) and read it back.

    A random value, so an old value left by another request can't make a
    broken cache look working. And a random KEY: with one shared key, two
    checks at the same moment (several in one process under ASGI) overwrite
    each other's value, and a healthy cache answers 503.
    aset() / aget() / adelete(): the async API of Django's cache.
    """
    value = uuid.uuid4().hex
    key = f"health_check:{value}"
    await cache.aset(key, value, timeout=10)
    try:
        if await cache.aget(key) != value:
            raise RuntimeError("the value read back differs from the value written")
    finally:
        await cache.adelete(key)  # no pile of keys; timeout=10 is the backup


CHECKS = {
    "database": check_database,
    "cache": check_cache,
}


async def run_check(name, check):
    """(name, "ok" | "error"); never raises."""
    try:
        await check()
    except Exception:
        # Any error counts: connection refused, timeout, wrong password...
        # logger.exception = ERROR level + the traceback
        logger.exception("Health check failed: %s", name)
        return name, "error"
    return name, "ok"


# Both decorators work with async views (Django 5.0+)
@never_cache  # Cache-Control: no-cache..., so no proxy or browser keeps an old answer
@require_GET  # other methods -> 405
async def health(request):
    """GET /health/ - is the app able to work right now?

    Used by the healthcheck of the web service in docker-compose.yml (and
    could be used by a load balancer or monitoring). Checks the services
    the app can't work without: PostgreSQL and Redis.

    200 {"status": "ok", "database": "ok", "cache": "ok"}
    503 {"status": "error", "database": "ok", "cache": "error"}

    503 Service Unavailable, not 500: the app itself works, a service it
    depends on doesn't. No login needed, so no session is read: the check
    works even when the session storage (Redis) is down.
    The error details go only to the log, not to the response: the URL is
    public, and an error message may reveal host names or settings.

    Async view: while it waits for PostgreSQL and Redis, the event loop of
    the worker serves other requests (a sync view would hold the worker).
    asyncio.gather() starts both checks together. Honest note: in Django
    6.1 the async ORM and the async cache API are still wrappers
    (sync_to_async, thread_sensitive=True) that run in one shared thread,
    so the two checks still go one after another; gather() makes the view
    ready for native async drivers without changes.
    """
    results = dict(
        await asyncio.gather(*(run_check(name, check) for name, check in CHECKS.items()))
    )

    healthy = all(result == "ok" for result in results.values())
    return JsonResponse(
        {"status": "ok" if healthy else "error", **results},
        status=200 if healthy else 503,
    )


# A cover keeps its name while it exists (a new upload gets a new name), but
# it may be deleted: a week, not "forever". The same as nginx/default.conf.
MEDIA_MAX_AGE = 7 * 24 * 60 * 60


@require_safe  # GET and HEAD only
def serve_media(request, path):
    """/media/<path>: an uploaded file (a book cover) from MEDIA_ROOT.

    Only with DEBUG (runserver) or SERVE_MEDIA (Railway, where no nginx
    stands in front of the app); otherwise 404, nginx serves /media/ there.
    Django's serve() view does the work: it refuses paths outside
    MEDIA_ROOT ("../"), sets the type from the extension, answers
    If-Modified-Since with 304. SecurityMiddleware adds "nosniff", so a file
    is never run as something else than its extension says.
    """
    if not (settings.DEBUG or settings.SERVE_MEDIA):
        raise Http404
    response = serve(request, path, document_root=settings.MEDIA_ROOT)
    patch_cache_control(response, public=True, max_age=MEDIA_MAX_AGE)
    return response


@require_POST
def set_language(request):
    """The language switcher in the navbar: POST language=uk|en, next=<page>.

    Django's own set_language view does the main work: checks the language,
    sets the "django_language" cookie and redirects back to `next` (only to
    an address of this site). On top of it the choice of a logged-in user
    is saved in the profile (User.language): the emails come in this
    language, and the login sets it on another device.
    """
    language = request.POST.get("language", "")
    if not is_supported_language(language):
        # Django's view checks only that Django itself has translations for
        # the code (it has "de", "fr", ... for the admin), not
        # settings.LANGUAGES, and would put "de" into the cookie. Without
        # "language" in POST it sets no cookie and only redirects back.
        request.POST = request.POST.copy()  # request.POST itself is read-only
        request.POST.pop("language", None)
    response = django_set_language(request)
    user = request.user
    if user.is_authenticated and is_supported_language(language) and user.language != language:
        user.language = language
        user.save(update_fields=["language"])
    return response


def sentry_debug(request):
    """/sentry-debug/: an error on purpose, to check Sentry end to end.

    Only for a superuser; anyone else gets 404, as if the URL didn't exist
    (a public URL that always fails would let bots fill the Sentry quota).
    The superuser gets templates/500.html (DEBUG=False) and Sentry gets
    a ZeroDivisionError with this request.
    """
    if not request.user.is_superuser:
        raise Http404
    logger.warning("Sentry check: raising ZeroDivisionError on purpose")
    return 1 / 0
