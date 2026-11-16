"""Cache invalidation: every change of the book data deletes its cache.

What is cached (books.cache): the Book object of the book page and the
HTML fragments of the catalog card and the book page. They contain the
book itself, its author's name and its categories, so all of these
changes must delete them:

    Book saved / deleted                -> that book
    Author saved (name)                 -> all books of the author
    Publisher saved (name)              -> all books of the publisher
    Category saved / deleted (name)     -> all books of the category
    Book <-> Category link changed      -> that book (or the books of
      (form, admin inline, .add())         the category, from its side)

The stock is NOT cached, so orders don't touch the cache at all.

Not covered: QuerySet.update() and raw SQL send no signals. The cache
timeout (BOOK_CACHE_TIMEOUT) is the safety net for them.
"""

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_books
from .models import Author, Book, BookCategory, Category, Publisher


@receiver([post_save, post_delete], sender=Book)
def book_changed(sender, instance, signal, **kwargs):
    invalidate_books([instance.pk], _reason("Book", signal))


@receiver(post_save, sender=Author)
def author_changed(sender, instance, **kwargs):
    # values_list: only the ids, one small query. An author with books
    # can't be deleted (PROTECT), so post_delete has nothing to clean.
    invalidate_books(instance.books.values_list("pk", flat=True), "Author saved")


@receiver(post_save, sender=Publisher)
def publisher_changed(sender, instance, **kwargs):
    # The same as the author: the name is shown on the book page. A
    # publisher with books can't be deleted (PROTECT)
    invalidate_books(instance.books.values_list("pk", flat=True), "Publisher saved")


@receiver([post_save, post_delete], sender=Category)
def category_changed(sender, instance, signal, **kwargs):
    invalidate_books(
        BookCategory.objects.filter(category=instance).values_list("book_id", flat=True),
        _reason("Category", signal),
    )


@receiver([post_save, post_delete], sender=BookCategory)
def book_category_saved(sender, instance, signal, **kwargs):
    """A link saved as an object: the admin inlines (BookCategoryInline,
    CategoryBookInline) save BookCategory rows one by one."""
    invalidate_books([instance.book_id], _reason("Book category link", signal))


@receiver(m2m_changed, sender=Book.categories.through)
def book_categories_changed(sender, instance, action, reverse, pk_set, **kwargs):
    """book.categories.add() / .set() / .remove() / .clear(): the form and the API.

    These send m2m_changed, not post_save of BookCategory.
    reverse=False: from the book's side, instance is the Book.
    reverse=True:  from the category's side (category.books.add(...)),
                   instance is the Category, pk_set the ids of the books.
    clear() has no pk_set, so from the category's side the books are
    taken in pre_clear, while the links still exist.
    """
    if action not in ("post_add", "post_remove", "pre_clear", "post_clear"):
        return
    reason = f"categories of a book changed ({action})"
    if not reverse:
        invalidate_books([instance.pk], reason)
    elif action == "pre_clear":
        invalidate_books(instance.books.values_list("pk", flat=True), reason)
    elif pk_set:
        invalidate_books(pk_set, reason)


def _reason(model_name, signal):
    """'Book saved' / 'Book deleted': what changed, for the log line."""
    return f"{model_name} {'deleted' if signal is post_delete else 'saved'}"
