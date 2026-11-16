"""The cached /api/authors/ and /api/categories/ (api.cache) are dropped
on every change that can change them: names, bios, slugs and books_count
(a book created, deleted, moved to another author or category).
Publisher: for the cached /api/publishers/ (the same rules).

Coarse on purpose: any change of these models starts a new generation.
They change rarely (a few edits a day), and a finer rule ("did the
count of this author change?") would be easy to get wrong.
"""

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from books.models import Author, Book, BookCategory, Category, Publisher

from .cache import invalidate_api_cache


@receiver([post_save, post_delete], sender=Author)
@receiver([post_save, post_delete], sender=Publisher)
@receiver([post_save, post_delete], sender=Category)
@receiver([post_save, post_delete], sender=Book)
@receiver([post_save, post_delete], sender=BookCategory)
@receiver(m2m_changed, sender=Book.categories.through)
def catalog_changed(sender, signal, **kwargs):
    action = kwargs.get("action")  # only m2m_changed has it
    if action and action.startswith("pre_"):
        return  # m2m_changed: only after the change, not before
    if action:
        reason = f"categories of a book changed ({action})"
    else:
        reason = f"{sender.__name__} {'deleted' if signal is post_delete else 'saved'}"
    invalidate_api_cache(reason)
