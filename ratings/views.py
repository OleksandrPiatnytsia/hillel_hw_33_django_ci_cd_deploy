from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from books.models import Book

from .models import Rating
from .services import can_rate


@require_POST
def rate(request, book_id):
    """POST /ratings/rate/<book_id>/ score=1..5 -> the user's score of the book, back to its page.

    The stars of the book page: five submit buttons name="score" (a click
    on the 4th star sends score=4). Only a customer who bought the book
    (can_rate), otherwise 403; a guest goes to the login page. A second
    score replaces the first one. A wrong score (0, 6, "abc"): a message,
    nothing saved.
    """
    book = get_object_or_404(Book, pk=book_id)
    page = book.get_absolute_url()
    if not request.user.is_authenticated:
        return redirect_to_login(page)
    if not can_rate(request.user, book):
        raise PermissionDenied("Only a customer who bought the book may rate it.")

    score = request.POST.get("score", "")
    if not score.isdigit() or not Rating.MIN_SCORE <= int(score) <= Rating.MAX_SCORE:
        messages.error(request, _("Choose from 1 to 5 stars."))
        return redirect(page)

    _rating, created = Rating.objects.update_or_create(
        user=request.user, book=book, defaults={"score": int(score)}
    )
    if created:
        messages.success(request, _("Thank you! Your rating is saved."))
    else:
        messages.success(request, _("Your rating is changed."))
    return redirect(page)
