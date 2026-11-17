"""The rating of a book: 1-5 stars from a customer who bought it.

The average and the count on the catalog card and the book page, the own
score of the customer, the sort "Best rated", the admin.
"""

import re

import pytest
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from books.models import Book
from orders.models import Order
from ratings.models import Rating
from ratings.services import can_rate, rating_context

from ..factories import BookFactory, CategoryFactory, OrderFactory, UserFactory
from ..helpers import message_levels

pytestmark = pytest.mark.django_db


def buy(user, book, **order):
    """A paid order of the user with the book (the default: new, paid)."""
    order.setdefault("payment_status", Order.PaymentStatus.PAID)
    return OrderFactory(user=user, items=[(book, 1)], **order)


def rate(client, book, score):
    return client.post(reverse("ratings:rate", args=[book.pk]), {"score": score})


def scores(*values):
    """A book with these scores from different users."""
    book = BookFactory()
    for value in values:
        Rating.objects.create(user=UserFactory(), book=book, score=value)
    return book


# ---------------------------------------------------------------------------
# Model and who may rate
# ---------------------------------------------------------------------------


# Generated with AI
def test_one_score_per_user_and_book_and_only_1_to_5(customer):
    book = BookFactory()
    Rating.objects.create(user=customer, book=book, score=4)

    with pytest.raises(IntegrityError), transaction.atomic():
        Rating.objects.create(user=customer, book=book, score=5)
    for wrong in (0, 6):
        with pytest.raises(IntegrityError), transaction.atomic():
            Rating.objects.create(user=UserFactory(), book=book, score=wrong)
    assert str(Rating.objects.get()) == f"ann → {book}: 4"


# Generated with AI
@pytest.mark.parametrize(
    "order, allowed",
    [
        ({}, True),  # paid
        ({"status": Order.Status.COMPLETED}, True),
        ({"payment_status": Order.PaymentStatus.UNPAID}, False),
        ({"payment_status": Order.PaymentStatus.PARTIALLY_PAID}, False),
        ({"status": Order.Status.CANCELLED}, False),
    ],
)
def test_only_a_customer_with_a_paid_order_may_rate(customer, order, allowed):
    book = BookFactory()
    buy(customer, book, **order)

    assert can_rate(customer, book) is allowed


# Generated with AI
def test_another_book_or_another_user_does_not_count(customer, other_customer):
    book, other = BookFactory(), BookFactory()
    buy(customer, other)
    buy(other_customer, book)

    assert can_rate(customer, book) is False


# Generated with AI
def test_guest_may_not_rate():
    from django.contrib.auth.models import AnonymousUser

    assert can_rate(AnonymousUser(), BookFactory()) is False


# ---------------------------------------------------------------------------
# The average: BookQuerySet.with_rating() and rating_context()
# ---------------------------------------------------------------------------


# Generated with AI
def test_with_rating_counts_once_also_with_a_category_join():
    poetry = CategoryFactory(slug="poetry")
    drama = CategoryFactory(slug="drama")
    book = scores(5, 4, 4)
    book.categories.set([poetry, drama])
    BookFactory(categories=[poetry])

    books = Book.objects.filter(categories__in=[poetry, drama]).distinct().with_rating()
    rated = books.get(pk=book.pk)

    assert rated.rating_count == 3
    assert rated.rating_avg == pytest.approx(13 / 3)
    unrated = books.exclude(pk=book.pk).get()
    assert unrated.rating_avg is None and unrated.rating_count == 0


# Generated with AI
def test_rating_context_of_a_customer(customer):
    book = scores(2, 4)
    assert rating_context(customer, book) == {
        "rating_avg": 3.0,
        "rating_count": 2,
        "my_score": None,
        "can_rate": False,
    }

    buy(customer, book)
    Rating.objects.create(user=customer, book=book, score=5)
    context = rating_context(customer, book)
    assert context["my_score"] == 5 and context["can_rate"] is True
    assert context["rating_count"] == 3


# ---------------------------------------------------------------------------
# Rating a book
# ---------------------------------------------------------------------------


# Generated with AI
def test_buyer_rates_and_changes_the_score(customer_client, customer):
    book = BookFactory()
    buy(customer, book)

    response = rate(customer_client, book, 4)
    assert response.status_code == 302 and response.url == book.get_absolute_url()
    assert message_levels(response) == ["success"]
    assert Rating.objects.get(user=customer, book=book).score == 4

    response = customer_client.post(
        reverse("ratings:rate", args=[book.pk]), {"score": 2}, follow=True
    )
    # The first message was not shown yet (no page between): both now
    messages = [str(m) for m in response.context["messages"]]
    assert messages == ["Дякуємо! Вашу оцінку збережено.", "Вашу оцінку змінено."]
    assert Rating.objects.get(user=customer, book=book).score == 2


# Generated with AI
def test_first_score_thanks_in_ukrainian(customer_client, customer):
    book = BookFactory()
    buy(customer, book)

    response = customer_client.post(
        reverse("ratings:rate", args=[book.pk]), {"score": 5}, follow=True
    )

    assert [str(m) for m in response.context["messages"]] == ["Дякуємо! Вашу оцінку збережено."]


# Generated with AI
@pytest.mark.parametrize("score", ["0", "6", "abc", ""])
def test_wrong_score_is_refused_with_a_message(customer_client, customer, score):
    book = BookFactory()
    buy(customer, book)

    response = rate(customer_client, book, score)

    assert response.url == book.get_absolute_url()
    assert message_levels(response) == ["error"]
    assert not Rating.objects.exists()


# Generated with AI
def test_not_a_buyer_gets_403(customer_client):
    book = BookFactory()

    assert rate(customer_client, book, 5).status_code == 403
    assert not Rating.objects.exists()


# Generated with AI
def test_guest_goes_to_the_login_and_back_to_the_book(client):
    book = BookFactory()

    response = rate(client, book, 5)

    assert response.url == f"{reverse('users:login')}?next={book.get_absolute_url()}"


# Generated with AI
def test_unknown_book_404_get_405_and_csrf(customer):
    client = Client()
    client.force_login(customer)
    assert client.post(reverse("ratings:rate", args=[999999]), {"score": 5}).status_code == 404
    book = BookFactory()
    assert client.get(reverse("ratings:rate", args=[book.pk])).status_code == 405

    strict = Client(enforce_csrf_checks=True)
    strict.force_login(customer)
    buy(customer, book)
    assert rate(strict, book, 5).status_code == 403


# ---------------------------------------------------------------------------
# The pages
# ---------------------------------------------------------------------------


# Generated with AI
def test_book_page_shows_the_average_and_the_count(client):
    book = scores(5, 4, 4)

    html = client.get(book.get_absolute_url()).content.decode()

    assert 'aria-label="Рейтинг 4,3 з 5"' in html
    assert 'style="width: 87%"' in html
    assert '<span class="fw-semibold">4,3</span>' in html
    assert "3 оцінки" in html
    # A guest gets no form and no hint
    assert "rate-form" not in html
    assert "Оцінити книгу можуть" not in html


# Generated with AI
def test_book_page_without_scores(client):
    html = client.get(BookFactory().get_absolute_url()).content.decode()

    assert "Ще немає оцінок" in html
    assert "rating-stars" not in html


# Generated with AI
def test_buyer_gets_the_stars_with_the_own_score_lit(customer_client, customer):
    book = BookFactory()
    buy(customer, book)

    html = customer_client.get(book.get_absolute_url()).content.decode()
    assert f'action="{reverse("ratings:rate", args=[book.pk])}"' in html
    assert "Оцініть книгу:" in html
    assert html.count('class="rate-star"') == 5

    Rating.objects.create(user=customer, book=book, score=3)
    html = customer_client.get(book.get_absolute_url()).content.decode()
    assert "Ваша оцінка:" in html
    stars = re.findall(r'<button class="rate-star( is-on)?"[^>]*value="(\d)"', html)
    assert [value for on, value in stars if on] == ["3", "2", "1"]
    assert 'value="3"' in html and 'aria-pressed="true"' in html
    assert 'aria-label="Оцінити на 4 з 5"' in html


# Generated with AI
def test_not_a_buyer_sees_who_may_rate(customer_client):
    html = customer_client.get(BookFactory().get_absolute_url()).content.decode()

    assert "Оцінити книгу можуть покупці" in html
    assert "rate-form" not in html


# Generated with AI
def test_new_score_shows_at_once_despite_the_cache(customer_client, customer):
    book = BookFactory()
    buy(customer, book)
    customer_client.get(book.get_absolute_url())  # the book and its fragments are cached
    customer_client.get(reverse("books:list"))

    rate(customer_client, book, 5)

    assert "1 оцінка" in customer_client.get(book.get_absolute_url()).content.decode()
    catalog = customer_client.get(reverse("books:list")).content.decode()
    assert '<span class="text-body-secondary">(1)</span>' in catalog


# Generated with AI
def test_catalog_card_shows_the_stars_only_with_scores(client):
    scores(5, 4)
    BookFactory()

    html = client.get(reverse("books:list")).content.decode()

    assert html.count("book-card-rating") == 1
    assert '<span class="fw-semibold">4,5</span>' in html
    assert '<span class="text-body-secondary">(2)</span>' in html


# Generated with AI
def test_wishlist_page_cards_have_the_stars_too(customer_client, customer):
    from wishlist.models import WishlistItem

    WishlistItem.objects.create(user=customer, book=scores(3))

    html = customer_client.get(reverse("wishlist:detail")).content.decode()

    assert "book-card-rating" in html


# Generated with AI
def test_catalog_sorts_by_rating(client):
    poetry = CategoryFactory(slug="poetry")
    good = scores(5, 4)
    best_sure = scores(5, 5, 5)
    best_once = scores(5)
    unrated = BookFactory(title="A unrated")
    for book in (good, best_sure, best_once, unrated):
        book.categories.add(poetry)

    # With a category filter too: its JOIN must not change the averages
    response = client.get(reverse("books:list"), {"sort": "-rating", "category": "poetry"})

    books = list(response.context["books"])
    # 5.0 of three scores before 5.0 of one; no scores at the end
    assert books == [best_sure, best_once, good, unrated]
    assert "Найкращий рейтинг" in response.content.decode()


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


# Generated with AI
def test_admin_lists_the_scores_and_can_not_add(superuser_client, customer):
    book = BookFactory(title="Kobzar")
    Rating.objects.create(user=customer, book=book, score=4)

    html = superuser_client.get(reverse("admin:ratings_rating_changelist")).content.decode()

    assert "Kobzar" in html and "ann" in html
    assert superuser_client.get(reverse("admin:ratings_rating_add")).status_code == 403
