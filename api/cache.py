"""Whole-response cache (cache_page) for /api/authors/ and /api/categories/.

Only these two: they change rarely and are the same for everybody. Not
/api/books/: a book in the JSON has "stock" and "in_stock", which change
with every order.

cache_page keys are built from the URL (and the headers of Vary), so they
can't be deleted one by one when an author changes: there are as many
as different URLs (?page=2, ?search=..., ?ordering=...). Instead every key
starts with a GENERATION number:

    api:<generation>:...views.decorators.cache.cache_page...<url hash>

invalidate_api_cache() adds 1 to it: all old responses are never read again
(they expire after API_CACHE_TIMEOUT) and the next request builds a new one.
No list of keys to keep and no FLUSHDB of the Redis database.
"""

import logging
import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.views.decorators.cache import cache_page

GENERATION_KEY = "api:cache_generation"

# Logs (logger "api.cache"):
#   DEBUG  API cache hit: /api/authors/ (generation 1731...)  - with DEBUG=True
#   DEBUG  API cache miss: /api/authors/ (generation 1731...)
#   INFO   API cache: new generation, old answers are not used (Author saved)
logger = logging.getLogger(__name__)


def _new_generation():
    # A number never used before (nanoseconds since 1970), for a counter
    # that is missing: 1 or 2 could be the generation of responses that
    # are still in the cache, if Redis evicted only the counter
    return time.time_ns()


def _generation():
    # timeout=None: the counter itself never expires (it is tiny)
    return cache.get_or_set(GENERATION_KEY, _new_generation, timeout=None)


def cache_api_response(view_func):
    """cache_page(API_CACHE_TIMEOUT) with the current generation in the keys.

    The decorator is built for every request: key_prefix of cache_page is
    fixed when it is created, and the generation can change at any time.
    Use on a ViewSet with method_decorator(cache_api_response, name="list").
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        generation = _generation()
        view_ran = False

        def run_view(*view_args, **view_kwargs):
            # Called by cache_page only when it has no answer in the cache
            nonlocal view_ran
            view_ran = True
            return view_func(*view_args, **view_kwargs)

        cached_view = cache_page(settings.API_CACHE_TIMEOUT, key_prefix=f"api:{generation}")(
            run_view
        )
        response = cached_view(request, *args, **kwargs)
        logger.debug(
            "API cache %s: %s (generation %s)",
            "miss" if view_ran else "hit",
            request.get_full_path(),
            generation,
        )
        return response

    return wrapper


def _next_generation():
    try:
        cache.incr(GENERATION_KEY)
    except ValueError:
        # No counter yet (or Redis lost it): a new number, see above
        cache.set(GENERATION_KEY, _new_generation(), timeout=None)


def invalidate_api_cache(reason):
    """Old cached responses are not used any more: now and after COMMIT.

    Twice for the same reason as books.cache.invalidate_books(): a request
    between the change and the COMMIT could cache the old data again.
    reason: what changed, only for the log.
    """
    logger.info("API cache: new generation, old answers are not used (%s)", reason)
    _next_generation()
    transaction.on_commit(_next_generation)
