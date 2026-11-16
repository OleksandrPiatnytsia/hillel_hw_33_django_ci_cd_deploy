"""Cache of the book data (Redis; LocMemCache in the tests).

Two kinds of cache, both WITHOUT the stock (it changes with every order
and is read fresh every time, see BookQuerySet.with_stock()):

1. Low-level cache: the Book object of the book page, with its author and
   categories, under the key "books:book:<pk>".
       get_cached_book(7) -> from Redis, or 2 queries + cache.set()

2. Template fragments ({% cache %} in book_list.html / book_detail.html):
   ready HTML of the parts of a book that are the same for every visitor.
   One fragment per book per language: the texts around the data
   ("Cover of ...", "Added ...") are translated.

Both are deleted by books.signals when a book, its author, a category or
the link book <-> category changes (invalidate_books()). The timeout is
only a safety net for a change that skips the signals (QuerySet.update()).

Logs (logger "books.cache", see LOGGING in settings):
    DEBUG  Book cache hit: id=7 / Book cache miss: id=7, cached for 3600 s
    INFO   Book cache cleared: ids=[7] (7 keys), reason: Book saved
DEBUG is shown only with DEBUG=True (APP_LOG_LEVEL). The hits of the
{% cache %} fragments are not logged: the template tag has no hook for it;
the fragments of a book are deleted together with its object (the same
"cleared" line, "7 keys" = 1 object + 3 fragments x 2 languages).
"""

import logging

from django.conf import settings
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.db import transaction

from .models import Book

# Names of the {% cache %} blocks in the templates. A new block with a book
# in its key must be added here, or it is never invalidated.
FRAGMENTS = ["book_card", "book_detail_header", "book_detail_body"]

logger = logging.getLogger(__name__)


def book_key(pk):
    return f"books:book:{pk}"


def get_cached_book(pk):
    """The book for the book page: from the cache, or from the database.

    Raises Book.DoesNotExist for an unknown pk (not cached: a missing book
    is cheap to look up, and caching "nothing" would need its own
    invalidation when the book is created).
    """
    key = book_key(pk)
    book = cache.get(key)
    if book is not None:
        logger.debug("Book cache hit: id=%s", pk)
    else:
        # The object goes into Redis pickled, with what it has loaded:
        # select_related -> the author and the publisher inside, prefetch_related -> the list
        # of categories inside. A cache hit then needs no query for them.
        book = (
            Book.objects.select_related("author", "publisher")
            .prefetch_related("categories")
            # The formats on sale (the tiles and the price of the book
            # page); books.signals drops the cache when a format changes
            .with_active_formats()
            .get(pk=pk)
        )
        # Never the stock or the availability: they would be stale after
        # the first order
        book.__dict__.pop("_stock", None)
        book.__dict__.pop("_available", None)
        cache.set(key, book, settings.BOOK_CACHE_TIMEOUT)
        logger.debug("Book cache miss: id=%s, cached for %s s", pk, settings.BOOK_CACHE_TIMEOUT)
    return book


def book_cache_keys(pks):
    """Every cache key that holds data of these books."""
    languages = [code for code, _name in settings.LANGUAGES]
    keys = []
    for pk in pks:
        keys.append(book_key(pk))
        # The same key {% cache ... name book.pk LANGUAGE_CODE %} makes
        keys += [
            make_template_fragment_key(name, [pk, language])
            for name in FRAGMENTS
            for language in languages
        ]
    return keys


def invalidate_books(pks, reason):
    """Delete the cached data of these books: now AND after COMMIT.

    reason: what changed ("Author saved"), only for the log.

    Now: the next request of this same process sees the change at once
    (and the tests, which never commit, see it too).
    After COMMIT: between "now" and the COMMIT another request still reads
    the OLD row from the database and may put it back into the cache;
    the second delete removes it. Outside a transaction on_commit() runs
    the function at once.
    """
    pks = sorted(set(pks))
    keys = book_cache_keys(pks)
    if not keys:
        return
    logger.info("Book cache cleared: ids=%s (%s keys), reason: %s", pks, len(keys), reason)
    cache.delete_many(keys)
    transaction.on_commit(lambda: cache.delete_many(keys))
