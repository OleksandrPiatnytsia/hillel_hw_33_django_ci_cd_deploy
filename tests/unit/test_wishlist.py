"""The wishlist: the hearts (add / remove), the page of the saved books, the navbar.

The heart is a POST form: static/js/wishlist.js sends it with
"Accept: application/json" and gets the new state; without JavaScript the
server answers with a message and a redirect back.
"""

import pytest
from django.contrib.admin.sites import site as admin_site
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from wishlist.models import WishlistItem
from wishlist.wishlist import Wishlist

from ..factories import BookFactory, UserFactory
from ..helpers import message_levels

pytestmark = pytest.mark.django_db

JSON = {"HTTP_ACCEPT": "application/json"}


def add(client, book, **extra):
    return client.post(reverse("wishlist:add", args=[book.pk]), **extra)


def remove(client, book, **extra):
    return client.post(reverse("wishlist:remove", args=[book.pk]), **extra)


def saved(user):
    return set(WishlistItem.objects.filter(user=user).values_list("book__title", flat=True))


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


# Generated with AI
def test_a_book_is_saved_once_per_user_by_the_database(customer, other_customer):
    book = BookFactory(title="Kobzar")
    WishlistItem.objects.create(user=customer, book=book)
    # Another user may save the same book
    WishlistItem.objects.create(user=other_customer, book=book)

    with pytest.raises(IntegrityError), transaction.atomic():
        WishlistItem.objects.create(user=customer, book=book)
    assert str(WishlistItem.objects.get(user=customer)) == f"ann ♥ {book}"


# Generated with AI
def test_deleting_the_book_or_the_user_deletes_the_rows(customer):
    book, other = BookFactory(), BookFactory()
    WishlistItem.objects.create(user=customer, book=book)
    WishlistItem.objects.create(user=customer, book=other)

    book.delete()
    assert WishlistItem.objects.count() == 1
    customer.delete()
    assert WishlistItem.objects.count() == 0


# Generated with AI
def test_wishlist_helper_knows_books_and_pks_with_one_query(customer, django_assert_num_queries):
    book, other = BookFactory(), BookFactory()
    WishlistItem.objects.create(user=customer, book=book)
    wishlist = Wishlist(customer)

    with django_assert_num_queries(1):
        assert book in wishlist and book.pk in wishlist
        assert other not in wishlist
        assert len(wishlist) == 1 and wishlist


# Generated with AI
def test_wishlist_helper_of_a_guest_is_empty_without_queries(client, django_assert_num_queries):
    from django.contrib.auth.models import AnonymousUser

    with django_assert_num_queries(0):
        wishlist = Wishlist(AnonymousUser())
        assert len(wishlist) == 0 and not wishlist and 1 not in wishlist


# ---------------------------------------------------------------------------
# Add / remove
# ---------------------------------------------------------------------------


# Generated with AI
def test_add_and_remove_without_javascript_redirect_back_with_a_message(customer_client, customer):
    book = BookFactory(title="Kobzar")

    response = add(customer_client, book, data={"next": "/?q=kob"})
    assert response.status_code == 302 and response.url == "/?q=kob"
    assert message_levels(response) == ["success"]
    assert saved(customer) == {"Kobzar"}

    response = remove(customer_client, book, data={"next": book.get_absolute_url()})
    assert response.url == book.get_absolute_url()
    assert saved(customer) == set()


# Generated with AI
def test_messages_in_ukrainian(customer_client):
    book = BookFactory(title="Kobzar")

    response = add(customer_client, book, follow=True)
    texts = [str(m) for m in response.context["messages"]]
    assert texts == ["«Kobzar» у вашому списку бажань."]

    response = remove(customer_client, book, follow=True)
    texts = [str(m) for m in response.context["messages"]]
    assert texts == ["«Kobzar» прибрано зі списку бажань."]


# Generated with AI
def test_add_and_remove_for_the_script_answer_with_json(customer_client, customer):
    book, other = BookFactory(), BookFactory()
    WishlistItem.objects.create(user=customer, book=other)

    data = add(customer_client, book, **JSON).json()
    assert data["saved"] is True
    assert data["url"] == reverse("wishlist:remove", args=[book.pk])
    assert saved(customer) == {book.title, other.title}

    data = remove(customer_client, book, **JSON).json()
    assert data["saved"] is False
    assert data["url"] == reverse("wishlist:add", args=[book.pk])
    assert saved(customer) == {other.title}
    # No flash message for the next page: the heart already shows it
    assert message_levels(customer_client.get(reverse("wishlist:detail"))) == []


# Generated with AI
def test_add_twice_and_remove_twice_change_nothing(customer_client, customer):
    book = BookFactory(title="Kobzar")

    add(customer_client, book)
    add(customer_client, book)
    assert WishlistItem.objects.filter(user=customer).count() == 1

    remove(customer_client, book)
    assert remove(customer_client, book).status_code == 302
    assert saved(customer) == set()


# Generated with AI
def test_remove_touches_only_the_own_wishlist(customer_client, customer, other_customer):
    book = BookFactory(title="Kobzar")
    WishlistItem.objects.create(user=other_customer, book=book)

    add(customer_client, book)
    remove(customer_client, book)

    assert saved(customer) == set()
    assert saved(other_customer) == {"Kobzar"}


# Generated with AI
def test_unknown_book_is_404_and_get_is_405(customer_client):
    assert customer_client.post(reverse("wishlist:add", args=[999999])).status_code == 404
    book = BookFactory()
    assert customer_client.get(reverse("wishlist:add", args=[book.pk])).status_code == 405
    assert customer_client.get(reverse("wishlist:remove", args=[book.pk])).status_code == 405


# Generated with AI
def test_next_of_another_site_is_refused(customer_client):
    response = add(customer_client, BookFactory(), data={"next": "https://evil.example/"})

    assert response.url == reverse("wishlist:detail")


# Generated with AI
def test_guest_is_sent_to_the_login_and_back_to_the_page(client):
    book = BookFactory()
    page = book.get_absolute_url()

    response = add(client, book, data={"next": page})
    assert response.status_code == 302
    assert response.url == f"{reverse('users:login')}?next={page}"

    assert remove(client, book, data={"next": page}).url == response.url

    response = add(client, book, data={"next": page}, **JSON)
    assert response.status_code == 401
    assert response.json() == {"login_url": f"{reverse('users:login')}?next={page}"}
    assert WishlistItem.objects.count() == 0


# Generated with AI
def test_csrf_is_checked(customer):
    client = Client(enforce_csrf_checks=True)
    client.force_login(customer)

    assert add(client, BookFactory()).status_code == 403


# ---------------------------------------------------------------------------
# The hearts in the pages
# ---------------------------------------------------------------------------


# Generated with AI
def test_catalog_cards_have_hearts_in_their_state(customer_client, customer):
    book = BookFactory(title="Kobzar")
    other = BookFactory(title="Zapovit")
    WishlistItem.objects.create(user=customer, book=book)

    html = customer_client.get(reverse("books:list")).content.decode()

    assert f'action="{reverse("wishlist:remove", args=[book.pk])}"' in html
    assert f'action="{reverse("wishlist:add", args=[other.pk])}"' in html
    assert html.count('aria-pressed="true"') == 1
    assert html.count('aria-pressed="false"') == 1
    assert 'title="Прибрати зі списку бажань"' in html
    assert 'title="Додати до списку бажань"' in html


# Generated with AI
def test_hearts_of_the_catalog_cost_one_query(customer_client, customer):
    books = [BookFactory() for _ in range(3)]
    WishlistItem.objects.create(user=customer, book=books[0])
    url = reverse("books:list")
    customer_client.get(url)  # warm up: session, cache of the cards, rates

    with CaptureQueriesContext(connection) as context:
        customer_client.get(url)
    queries = [q["sql"] for q in context.captured_queries if "wishlist_wishlistitem" in q["sql"]]
    # One for all the hearts of the page
    assert len(queries) == 1


# Generated with AI
def test_cached_card_does_not_keep_the_heart_of_another_user(
    customer_client, customer, other_customer
):
    book = BookFactory()
    WishlistItem.objects.create(user=customer, book=book)
    customer_client.get(reverse("books:list"))  # the card fragment is cached on this visit

    bob = Client()
    bob.force_login(other_customer)
    html = bob.get(reverse("books:list")).content.decode()

    assert f'action="{reverse("wishlist:add", args=[book.pk])}"' in html
    assert 'aria-pressed="true"' not in html


# Generated with AI
def test_book_page_has_the_heart_with_a_text_under_the_cart_button(customer_client, customer):
    book = BookFactory()
    url = book.get_absolute_url()

    html = customer_client.get(url).content.decode()
    # Under the "Add to cart" button, in the block of the purchase
    assert html.index(">У кошик</button>") < html.index('<div class="book-wishlist mt-2">')
    row = html[html.index('<div class="book-wishlist mt-2">') :]
    assert "wishlist-heart--page" in row
    assert "До списку бажань" in row

    WishlistItem.objects.create(user=customer, book=book)
    html = customer_client.get(url).content.decode()
    assert "У списку бажань" in html
    assert 'data-text-add="До списку бажань" data-text-saved="У списку бажань"' in html


# Generated with AI
def test_guest_gets_a_link_to_the_login_instead_of_the_form(client):
    book = BookFactory()

    html = client.get(book.get_absolute_url()).content.decode()

    assert reverse("wishlist:add", args=[book.pk]) not in html
    assert f'href="{reverse("users:login")}?next={book.get_absolute_url()}"' in html
    assert "Увійдіть, щоб зберігати книги до списку бажань" in html
    # No navbar link of the wishlist for a guest
    assert f'href="{reverse("wishlist:detail")}"' not in html


# Generated with AI
def test_navbar_has_only_the_user_menu_link(customer_client, customer):
    WishlistItem.objects.create(user=customer, book=BookFactory())

    html = customer_client.get(reverse("books:list")).content.decode()

    # A menu item of the user, no heart with a counter in the navbar itself
    assert html.count(f'href="{reverse("wishlist:detail")}"') == 1
    assert f'<a class="dropdown-item" href="{reverse("wishlist:detail")}">Список бажань</a>' in html
    assert "data-wishlist-count" not in html


# Generated with AI
def test_profile_shows_the_count_with_a_link(customer_client, customer):
    WishlistItem.objects.create(user=customer, book=BookFactory())

    html = customer_client.get(reverse("users:profile")).content.decode()

    assert ">Список бажань</dt>" in html
    assert "1 книга</a>" in html


# ---------------------------------------------------------------------------
# The wishlist page
# ---------------------------------------------------------------------------


# Generated with AI
def test_wishlist_page_lists_only_own_books_the_last_saved_first(
    customer_client, customer, other_customer
):
    first = BookFactory(title="Kobzar")
    second = BookFactory(title="Zapovit")
    foreign = BookFactory(title="Eneida")
    item = WishlistItem.objects.create(user=customer, book=first)
    WishlistItem.objects.filter(pk=item.pk).update(
        created_at=timezone.now() - timezone.timedelta(days=1)
    )
    WishlistItem.objects.create(user=customer, book=second)
    WishlistItem.objects.create(user=other_customer, book=foreign)

    response = customer_client.get(reverse("wishlist:detail"))

    assert [book.title for book in response.context["books"]] == ["Zapovit", "Kobzar"]
    html = response.content.decode()
    assert "Eneida" not in html
    assert "2 книги" in html
    # Catalog cards: with the button of the cart and a filled heart
    assert html.count("data-wishlist-card") == 2
    assert html.count('aria-pressed="true"') == 2
    assert reverse("cart:add", args=[first.pk]) in html


# Generated with AI
def test_wishlist_page_when_empty(customer_client):
    html = customer_client.get(reverse("wishlist:detail")).content.decode()

    assert "Ваш список бажань порожній" in html
    assert f'href="{reverse("books:list")}"' in html


# Generated with AI
def test_wishlist_page_needs_login(client):
    url = reverse("wishlist:detail")

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('users:login')}?next={url}"


# Generated with AI
def test_wishlist_page_is_paginated(customer_client, customer):
    for _ in range(25):
        WishlistItem.objects.create(user=customer, book=BookFactory())

    response = customer_client.get(reverse("wishlist:detail"))

    assert len(response.context["books"]) == 24
    assert customer_client.get(reverse("wishlist:detail") + "?page=2").status_code == 200


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


# Generated with AI
def test_admin_lists_the_rows_and_can_not_add(superuser_client, customer):
    WishlistItem.objects.create(user=customer, book=BookFactory(title="Kobzar"))

    html = superuser_client.get(reverse("admin:wishlist_wishlistitem_changelist")).content.decode()

    assert "Kobzar" in html and "ann" in html
    assert superuser_client.get(reverse("admin:wishlist_wishlistitem_add")).status_code == 403
    assert WishlistItem in admin_site._registry


# Generated with AI
def test_user_factory_is_fine_with_wishlists():
    # A user made by the factory starts with an empty wishlist
    assert len(Wishlist(UserFactory())) == 0
