"""Who may rate a book, and the rating data of the book page."""

from django.db.models import Avg, Count

from orders.models import Order, OrderItem

from .models import Rating


def can_rate(user, book):
    """True if the user bought the book: a paid order with it, not cancelled.

    Paid, not only ordered: a new unpaid order can be cancelled by its
    timeout (cancel_unpaid_orders), and the rating would stay. Any format
    of the book counts.
    """
    if not user.is_authenticated:
        return False
    return (
        OrderItem.objects.filter(
            book=book,
            order__user=user,
            order__payment_status=Order.PaymentStatus.PAID,
        )
        .exclude(order__status=Order.Status.CANCELLED)
        .exists()
    )


def rating_context(user, book):
    """The rating block of the book page (books/book_detail.html).

    Read fresh on every visit, not from the cached book: a new score shows
    at once. One query for the average and the count; for a logged-in user
    one more for the own score and one for can_rate().

        rating_avg   4.333... or None (no scores yet)
        rating_count 3
        my_score     4 or None (not rated yet)
        can_rate     True: show the stars to click
    """
    stats = Rating.objects.filter(book=book).aggregate(avg=Avg("score"), count=Count("pk"))
    my_score = None
    allowed = False
    if user.is_authenticated:
        my_score = (
            Rating.objects.filter(user=user, book=book).values_list("score", flat=True).first()
        )
        # Who rated once has bought it: no second query
        allowed = my_score is not None or can_rate(user, book)
    return {
        "rating_avg": stats["avg"],
        "rating_count": stats["count"],
        "my_score": my_score,
        "can_rate": allowed,
    }
