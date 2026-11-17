from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class Rating(models.Model):
    """The score a customer gave a book: 1 to 5 stars, one per user and book.

    Only a customer who bought the book may rate it (ratings.services.
    can_rate): a paid order with the book that is not cancelled. A new
    score of the same user replaces the old one (update_or_create).
    Of the book, not of a format: the paper book and the e-book are the
    same text.
    The average and the count are not stored on the book: they are
    calculated by the database (BookQuerySet.with_rating) and always fresh.
    Deleting the user or the book deletes the score (CASCADE).
    """

    MIN_SCORE = 1
    MAX_SCORE = 5

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ratings",
        verbose_name=_("user"),
    )
    book = models.ForeignKey(
        "books.Book",
        on_delete=models.CASCADE,
        related_name="ratings",
        verbose_name=_("book"),
    )
    score = models.PositiveSmallIntegerField(
        _("score"),
        validators=[MinValueValidator(MIN_SCORE), MaxValueValidator(MAX_SCORE)],
    )
    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("rating")
        verbose_name_plural = _("ratings")
        ordering = ["-updated_at"]
        constraints = [
            # One score per user and book, also for two clicks at once
            models.UniqueConstraint(fields=["user", "book"], name="ratings_unique_user_book"),
            # The validators run only in forms and full_clean(); the database
            # refuses a 0 or a 6 from any code
            models.CheckConstraint(
                condition=models.Q(score__gte=1, score__lte=5),
                name="ratings_score_1_to_5",
            ),
        ]

    def __str__(self):
        return f"{self.user} → {self.book}: {self.score}"
