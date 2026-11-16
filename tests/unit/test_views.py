"""Unit tests of the views: one request -> status code, redirect, context.

Whole user flows (several requests in a row) are in tests/integration/.
"""

import re

import pytest
from django.urls import reverse
from pytest_django.asserts import assertRedirects, assertTemplateUsed

from config import views as config_views
from orders.models import Order

from ..factories import AuthorFactory, BookFactory, CategoryFactory, OrderFactory, PaymentFactory
from ..fakes import stripe_event_payload, stripe_webhook_headers
from ..helpers import message_levels

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_book_list_filters_by_search_and_category(client):
    poetry = CategoryFactory(name="Poetry", slug="poetry")
    BookFactory(title="Kobzar", author__name="Taras Shevchenko", categories=[poetry])
    BookFactory(title="Kobzar for kids", author__name="Someone Else")
    BookFactory(title="Zakhar Berkut", author__name="Ivan Franko")

    response = client.get(reverse("books:list"), {"q": "kobzar", "category": "poetry"})

    assert response.status_code == 200
    assertTemplateUsed(response, "books/book_list.html")
    assert [book.title for book in response.context["books"]] == ["Kobzar"]


def test_book_list_filters_by_several_authors(client):
    """?author=1&author=5: books of any of them (OR inside one filter)."""
    shevchenko, franko = AuthorFactory(name="Taras Shevchenko"), AuthorFactory(name="Ivan Franko")
    BookFactory(title="Kobzar", author=shevchenko)
    BookFactory(title="Zakhar Berkut", author=franko)
    BookFactory(title="Lisova pisnia", author__name="Lesia Ukrainka")

    response = client.get(reverse("books:list"), {"author": [shevchenko.pk, franko.pk]})

    assert [book.title for book in response.context["books"]] == ["Kobzar", "Zakhar Berkut"]


def test_book_list_several_categories_give_each_book_once(client):
    """A book in two of the chosen categories is not repeated (EXISTS, not a JOIN)."""
    poetry = CategoryFactory(name="Poetry", slug="poetry")
    classics = CategoryFactory(name="Classics", slug="classics")
    BookFactory(title="Kobzar", categories=[poetry, classics])
    BookFactory(title="Zakhar Berkut", categories=[classics])
    BookFactory(title="Other", categories=[CategoryFactory()])

    response = client.get(reverse("books:list"), {"category": ["poetry", "classics"]})

    assert [book.title for book in response.context["books"]] == ["Kobzar", "Zakhar Berkut"]
    assert response.context["paginator"].count == 2


def test_book_list_different_filters_are_combined_with_and(client):
    poetry = CategoryFactory(name="Poetry", slug="poetry")
    shevchenko = AuthorFactory(name="Taras Shevchenko")
    BookFactory(title="Kobzar", author=shevchenko, categories=[poetry])
    BookFactory(title="Haidamaky", author=shevchenko)
    BookFactory(title="Other poems", categories=[poetry])

    response = client.get(reverse("books:list"), {"author": shevchenko.pk, "category": "poetry"})

    assert [book.title for book in response.context["books"]] == ["Kobzar"]


def test_book_list_chips_remove_one_value_each(client):
    """Every chosen value is a chip; its link is the page without this value only."""
    poetry = CategoryFactory(name="Poetry", slug="poetry")
    shevchenko, franko = AuthorFactory(name="Taras Shevchenko"), AuthorFactory(name="Ivan Franko")
    BookFactory(author=shevchenko, categories=[poetry])

    response = client.get(
        reverse("books:list"),
        {
            "q": "ko",
            "category": "poetry",
            "author": [shevchenko.pk, franko.pk],
            "price_min": "100.00",
            "sort": "-price",
            "page": "1",
        },
    )
    chips = {chip["label"]: chip["url"] for chip in response.context["filter_chips"]}
    s, f = shevchenko.pk, franko.pk

    assert list(chips) == [
        "Пошук: “ko”",
        "Poetry",
        # in the panel order: authors by name, not in the order of the URL
        "Ivan Franko",
        "Taras Shevchenko",
        "Ціна: від 100 ₴",
    ]
    # The page number is dropped: the longer list starts from page 1
    assert chips["Taras Shevchenko"] == (
        f"?q=ko&category=poetry&author={f}&price_min=100.00&sort=-price"
    )
    assert chips["Poetry"] == f"?q=ko&author={s}&author={f}&price_min=100.00&sort=-price"
    assert chips["Ціна: від 100 ₴"] == f"?q=ko&category=poetry&author={s}&author={f}&sort=-price"
    # "Clear all": only the sort stays
    assert response.context["filter_reset_url"] == "?sort=-price"
    html = response.content.decode()
    assert "Очистити все" in html
    assert (
        f'href="?q=ko&amp;category=poetry&amp;author={f}&amp;price_min=100.00&amp;sort=-price"'
        in html
    )


def test_book_list_price_chip_shows_the_range_in_the_chosen_currency(client):
    response = client.get(reverse("books:list"), {"price_min": "99.50", "price_max": "500"})

    [chip] = response.context["filter_chips"]
    assert chip == {"label": "Ціна: 99.5–500 ₴", "url": "?"}


def test_book_list_no_filters_no_chips(client):
    response = client.get(reverse("books:list"), {"sort": "-price"})

    assert response.context["filter_chips"] == []
    assert "Очистити все" not in response.content.decode()


def test_book_list_wrong_value_gets_no_chip(client):
    response = client.get(reverse("books:list"), {"category": "deleted-category", "stock": "low"})

    assert [chip["label"] for chip in response.context["filter_chips"]] == ["Мало (≤ 5)"]


def test_book_list_panel_has_a_folding_block_per_filter_with_chosen_boxes(client):
    """Every filter is a block that folds; the chosen values are ticked."""
    shevchenko = AuthorFactory(name="Taras Shevchenko")
    AuthorFactory.create_batch(6)  # a long list: a search box over it
    CategoryFactory(name="Poetry", slug="poetry")

    html = client.get(reverse("books:list"), {"author": shevchenko.pk, "stock": "low"}).text

    for name in ("category", "author", "stock", "price"):
        assert f'data-bs-target="#filter-{name}"' in html
    # The text search is the one in the navbar, not a block of the panel
    assert 'data-bs-target="#filter-q"' not in html
    assert f'type="checkbox" name="author" value="{shevchenko.pk}" class="form-check-input"' in html
    assert re.search(rf'value="{shevchenko.pk}"[^>]*checked', html)
    assert re.search(r'type="radio" name="stock" value="low"[^>]*checked', html)
    # 7 authors: search + "Show all"; 1 category: neither
    assert html.count("data-option-search") == 1
    assert html.count("data-show-all") == 1
    assert "js/filter_panel.js" in html
    assert "<noscript>" in html  # "Apply" without JavaScript


def test_book_list_panel_keeps_the_search_of_the_navbar(client):
    """A checkbox sends the panel form: the ?q= of the navbar must go with it."""
    html = client.get(reverse("books:list"), {"q": "kobzar"}).text

    assert '<input type="hidden" name="q" value="kobzar">' in html


def test_book_list_sorts_by_price(client):
    BookFactory(title="Cheap", price=50)
    BookFactory(title="Expensive", price=500)

    response = client.get(reverse("books:list"), {"sort": "-price"})

    assert [book.title for book in response.context["books"]] == ["Expensive", "Cheap"]


# Generated with AI
def test_book_list_sorts_by_popularity_without_cancelled_orders(client):
    poetry = CategoryFactory(name="Poetry", slug="poetry")
    hit = BookFactory(title="Hit", categories=[poetry])
    steady = BookFactory(title="Steady", categories=[poetry])
    BookFactory(title="A never ordered", categories=[poetry])
    cancelled_only = BookFactory(title="B cancelled", categories=[poetry])
    OrderFactory(items=[(hit, 3), (steady, 1)])
    OrderFactory(items=[(steady, 1)])
    OrderFactory(items=[(cancelled_only, 10)], status=Order.Status.CANCELLED)

    # With a category filter too: its JOIN must not count the copies twice
    response = client.get(reverse("books:list"), {"sort": "-sold", "category": "poetry"})

    books = response.context["books"]
    # 0 sold: by title; the cancelled order counts for nothing
    assert [book.title for book in books] == ["Hit", "Steady", "A never ordered", "B cancelled"]
    assert [book.sold for book in books] == [3, 2, 0, 0]
    assert "Спершу популярні" in response.text


# Generated with AI
def test_book_list_puts_out_of_stock_books_last_by_default(client):
    BookFactory(title="A gone", price=50, stock=0)
    BookFactory(title="B cheap", price=100, stock=3)
    BookFactory(title="C dear", price=500, stock=1)
    BookFactory(title="D gone too", price=900, stock=0)

    by_price = client.get(reverse("books:list"), {"sort": "price"})
    switched_off = client.get(reverse("books:list"), {"sort": "price", "out_last": "0"})

    # The sort works inside both groups: in stock by price, then the rest by price
    assert [book.title for book in by_price.context["books"]] == [
        "B cheap",
        "C dear",
        "A gone",
        "D gone too",
    ]
    assert [book.title for book in switched_off.context["books"]] == [
        "A gone",
        "B cheap",
        "C dear",
        "D gone too",
    ]


# Generated with AI
def test_out_of_stock_last_checkbox_is_a_link_that_keeps_the_other_parameters(client):
    BookFactory()

    on = client.get(reverse("books:list"), {"sort": "-price", "page": "1"}).text
    off = client.get(reverse("books:list"), {"sort": "-price", "out_last": "0"}).text

    assert 'aria-checked="true"' in on
    assert 'href="?sort=-price&amp;out_last=0"' in on  # page dropped
    assert 'aria-checked="false"' in off
    assert 'href="?sort=-price"' in off
    # "Apply" of the filters keeps it off
    assert '<input type="hidden" name="out_last" value="0">' in off
    assert "Відсутні в кінці" in on


def test_book_list_wrong_parameter_keeps_the_other_filters(client):
    """AI review (AI_REVIEW.md, BookListView): an invalid ?category= used to
    drop ALL filters and show the whole catalog."""
    BookFactory(title="Kobzar")
    BookFactory(title="Zakhar Berkut")

    response = client.get(reverse("books:list"), {"q": "kobzar", "category": "deleted-category"})

    assert "category" in response.context["filter_form"].errors  # the error is shown
    assert [book.title for book in response.context["books"]] == ["Kobzar"]


def test_book_list_price_from_greater_than_to_ignores_only_prices(client):
    BookFactory(title="Kobzar", price=100)
    BookFactory(title="Zakhar Berkut", price=200)

    response = client.get(
        reverse("books:list"), {"q": "kobzar", "price_min": "500", "price_max": "100"}
    )

    assert response.context["filter_form"].non_field_errors()
    assert [book.title for book in response.context["books"]] == ["Kobzar"]


def test_book_list_order_always_ends_with_pk(client):
    """Books with an equal title / price must not jump between pages."""
    # out_last=0: only the sort itself (by default "out of stock last" goes first)
    response = client.get(reverse("books:list"), {"out_last": "0"})

    assert response.context["paginator"].object_list.query.order_by == ("title", "pk")


def test_book_list_sorts_by_the_converted_price_then_pk(client):
    response = client.get(reverse("books:list"), {"sort": "-price"})

    # "-price" in the URL: the database sorts by the price in the currency
    # of the switcher (annotation display_price), books without it last
    out_of_stock_last, by_price, tie_breaker = response.context[
        "paginator"
    ].object_list.query.order_by
    assert "stock" in str(out_of_stock_last)  # CASE WHEN stock = 0 THEN 1 ELSE 0
    assert (by_price.expression.name, by_price.descending, by_price.nulls_last) == (
        "display_price",
        True,
        True,
    )
    assert tie_breaker == "pk"


@pytest.mark.parametrize(
    ("per_page", "expected"),
    [
        (None, 12),  # no parameter: the default
        ("24", 24),
        ("48", 48),
        ("100000", 12),  # not in the list: the whole catalog in one page is not allowed
        ("abc", 12),  # an old or broken link: the default page, not an error
    ],
)
def test_book_list_per_page(client, per_page, expected):
    BookFactory.create_batch(50)
    params = {"per_page": per_page} if per_page else {}

    response = client.get(reverse("books:list"), params)

    assert response.status_code == 200
    assert response.context["per_page"] == expected
    assert len(response.context["books"]) == expected


def test_book_list_per_page_is_kept_by_filters_and_pagination(client):
    """The chosen "Per page" survives "Apply" in the filters (hidden field)
    and the page links ({% querystring %}); the dropdown keeps the filters
    and drops "page" (page 3 of 12 books may not exist with 48)."""
    BookFactory.create_batch(30, title="Kobzar")

    response = client.get(reverse("books:list"), {"q": "kobzar", "per_page": "24", "page": "2"})
    html = response.content.decode()

    assert '<input type="hidden" name="per_page" value="24">' in html  # filters form
    assert "?q=kobzar&amp;per_page=24&amp;page=1" in html  # pagination link
    assert '<input type="hidden" name="q" value="kobzar">' in html  # dropdown form
    assert '<input type="hidden" name="page"' not in html
    assert '<option value="24" selected>' in html


def test_book_list_default_per_page_adds_no_hidden_field(client):
    response = client.get(reverse("books:list"))

    assert 'name="per_page" value=' not in response.content.decode()


def test_book_list_sort_dropdown_keeps_the_filters(client):
    """The sort is a dropdown of links next to "Per page", not a field of
    the filters: every link keeps the filters and "Per page", drops the page
    number and marks the current sort."""
    BookFactory.create_batch(30, title="Kobzar")

    response = client.get(
        reverse("books:list"), {"q": "kobzar", "per_page": "24", "sort": "-price", "page": "2"}
    )
    html = response.content.decode()

    assert response.context["sort"] == "-price"
    # The button shows the current sort (in the language of the page)
    assert f": {response.context['sort_label']}\n" in html
    assert 'href="?q=kobzar&amp;per_page=24&amp;sort=price"' in html  # page dropped
    assert re.search(r'class="dropdown-item active"\s+href="\?[^"]*sort=-price"', html)
    assert 'name="sort"' not in html.replace('<input type="hidden" name="sort"', "")


def test_book_list_apply_keeps_the_sort_and_reset_keeps_it_too(client):
    """ "Apply" sends the current sort in a hidden field; "Reset" clears only
    the filters, the sort and "Per page" stay."""
    response = client.get(
        reverse("books:list"), {"q": "kobzar", "stock": "in", "per_page": "24", "sort": "-price"}
    )
    html = response.content.decode()

    assert '<input type="hidden" name="sort" value="-price">' in html
    assert 'href="?per_page=24&amp;sort=-price">' in html  # Reset


def test_book_list_default_sort_adds_no_hidden_field(client):
    response = client.get(reverse("books:list"))

    assert response.context["sort"] == "title"
    assert '<input type="hidden" name="sort"' not in response.content.decode()


def test_book_detail_shows_quantity_in_cart(client):
    book = BookFactory()
    client.post(reverse("cart:add", args=[book.pk]), {"quantity": 2})

    response = client.get(book.get_absolute_url())

    assert response.status_code == 200
    assert response.context["in_cart"] == 2


def test_missing_book_is_404(client):
    assert client.get(reverse("books:detail", args=[999999])).status_code == 404


@pytest.mark.parametrize(
    ("client_fixture", "expected_status"),
    [("customer_client", 403), ("manager_client", 200)],
)
def test_book_create_needs_permission(request, client_fixture, expected_status):
    # request.getfixturevalue(): a fixture chosen by name from the parameters
    client = request.getfixturevalue(client_fixture)

    assert client.get(reverse("books:create")).status_code == expected_status


def test_author_list_counts_books(client):
    book = BookFactory(author__name="Lesya Ukrainka")
    BookFactory(author=book.author)

    response = client.get(reverse("books:author_list"))

    assert response.context["authors"][0].books_count == 2


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------


def test_cart_add_accepts_only_post(client):
    book = BookFactory()

    assert client.get(reverse("cart:add", args=[book.pk])).status_code == 405


def test_cart_add_redirects_back_only_to_own_site(client):
    book = BookFactory()
    url = reverse("cart:add", args=[book.pk])

    same_site = client.post(url, {"quantity": 1, "next": "/?page=2"})
    other_site = client.post(url, {"quantity": 1, "next": "https://evil.example/"})

    assertRedirects(same_site, "/?page=2", fetch_redirect_response=False)
    assertRedirects(other_site, reverse("cart:detail"))


def test_cart_add_more_than_stock_warns(client):
    book = BookFactory(stock=2)

    response = client.post(reverse("cart:add", args=[book.pk]), {"quantity": 5})

    assert message_levels(response) == ["warning"]
    assert client.session["cart"] == {str(book.pk): {"quantity": 2}}


@pytest.mark.parametrize("quantity", ["0", "-1", "two"])
def test_cart_add_with_wrong_quantity_is_an_error(client, quantity):
    book = BookFactory()

    response = client.post(reverse("cart:add", args=[book.pk]), {"quantity": quantity})

    assert message_levels(response) == ["error"]
    assert not client.session.get("cart")


def test_cart_add_out_of_stock_book_is_an_error(client):
    book = BookFactory(stock=0)

    response = client.post(reverse("cart:add", args=[book.pk]), {"quantity": 1})

    assert message_levels(response) == ["error"]


def test_cart_remove_and_clear(client):
    first, second = BookFactory(), BookFactory()
    for book in (first, second):
        client.post(reverse("cart:add", args=[book.pk]), {"quantity": 1})

    removed = client.post(reverse("cart:remove", args=[first.pk]))
    assert list(client.session["cart"]) == [str(second.pk)]
    assert message_levels(removed)[-1] == "success"

    cleared = client.post(reverse("cart:clear"))
    assertRedirects(cleared, reverse("cart:detail"))
    assert not client.session.get("cart")


# ---------------------------------------------------------------------------
# Orders and payments: access rules
# ---------------------------------------------------------------------------


def test_checkout_needs_login(client):
    url = reverse("orders:checkout")

    assertRedirects(client.get(url), f"{reverse('users:login')}?next={url}")


def test_checkout_with_empty_cart_goes_to_cart(customer_client):
    response = customer_client.get(reverse("orders:checkout"))

    assertRedirects(response, reverse("cart:detail"))


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_checkout_accepts_only_get_and_post(customer_client, method):
    """AI review (AI_REVIEW.md, checkout): other methods got the form with 200."""
    response = getattr(customer_client, method)(reverse("orders:checkout"))

    assert response.status_code == 405


def test_checkout_form_is_prefilled_from_profile(customer, customer_client):
    customer.phone, customer.address = "+380671234567", "Kyiv"
    customer.save()
    customer_client.post(reverse("cart:add", args=[BookFactory().pk]), {"quantity": 1})

    response = customer_client.get(reverse("orders:checkout"))

    assert response.context["form"].initial == {
        "currency": "UAH",  # the currency of the cart
        "full_name": "Ann Shevchenko",
        "phone": "+380671234567",
        "address": "Kyiv",
    }


def test_someone_elses_order_is_404(customer, other_customer_client):
    order = OrderFactory(user=customer)

    assert other_customer_client.get(order.get_absolute_url()).status_code == 404
    response = other_customer_client.post(reverse("orders:cancel", args=[order.pk]))
    assert response.status_code == 404
    order.refresh_from_db()
    assert order.status == Order.Status.NEW


def test_my_orders_lists_only_own_orders_with_books_count(
    customer, other_customer, customer_client
):
    mine = OrderFactory(user=customer, items=[(BookFactory(), 2), (BookFactory(), 1)])
    OrderFactory(user=other_customer)

    response = customer_client.get(reverse("orders:list"))

    orders = list(response.context["orders"])
    assert orders == [mine]
    assert orders[0].books_count == 3


def test_payment_success_with_someone_elses_session_is_404(
    customer, other_customer_client, fake_stripe
):
    payment = PaymentFactory(order__user=customer)

    response = other_customer_client.get(
        reverse("payments:success"), {"session_id": payment.external_id}
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Webhook: requests that are refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["manual", "paypal"])
def test_webhook_of_provider_without_webhooks_is_404(client, provider):
    response = client.post(
        reverse("payments:webhook", args=[provider]), data="{}", content_type="application/json"
    )

    assert response.status_code == 404


def test_webhook_with_wrong_signature_is_400(client):
    payload = stripe_event_payload("checkout.session.completed", "cs_test_1")

    response = client.post(
        reverse("payments:webhook", args=["stripe"]),
        data=payload,
        content_type="application/json",
        headers=stripe_webhook_headers(payload, secret="whsec_somebody_else"),
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def test_profile_edit_saves_own_data(customer, customer_client):
    response = customer_client.post(
        reverse("users:profile_edit"),
        {"first_name": "Anna", "last_name": "S", "phone": "+380 67 765 43 21", "address": "Odesa"},
    )

    assertRedirects(response, reverse("users:profile"))
    customer.refresh_from_db()
    assert (customer.first_name, customer.phone, customer.address) == (
        "Anna",
        "+380677654321",
        "Odesa",
    )


def test_logged_in_user_is_sent_away_from_sign_up(customer_client):
    response = customer_client.get(reverse("users:signup"))

    assertRedirects(response, reverse("books:list"))


# ---------------------------------------------------------------------------
# Project-level: /health/ and the timing middleware
# ---------------------------------------------------------------------------


def test_health_ok(client):
    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "cache": "ok"}


def test_health_reports_broken_cache_with_503(client, monkeypatch):
    async def broken_cache():  # the checks are async functions now
        raise ConnectionError("Redis is down (test)")

    # CHECKS is a dict: replace one entry for this test only
    monkeypatch.setitem(config_views.CHECKS, "cache", broken_cache)

    response = client.get(reverse("health"))

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "ok", "cache": "error"}


def test_every_response_has_timing_headers(client):
    response = client.get(reverse("books:list"))

    assert response["X-Request-Duration"].endswith("ms")
    assert response["Server-Timing"].startswith("app;dur=")


# ---------------------------------------------------------------------------
# Profile: "Tools" (users/tools.py), superuser only
# ---------------------------------------------------------------------------


def tool_links(response):
    return {
        tool.title: tool.url for _group, tools in response.context["tool_groups"] for tool in tools
    }


# Generated with AI
def test_superuser_sees_the_tools_and_every_link_works(superuser_client, settings):
    settings.FLOWER_URL = "http://localhost:5555"
    settings.SENTRY_ISSUES_URL = "https://example.sentry.io/issues/?project=1"
    settings.STRIPE_SECRET_KEY = "sk_test_fake"

    response = superuser_client.get(reverse("users:profile"))

    links = tool_links(response)
    assert links["Flower"] == "http://localhost:5555"
    assert links["Sentry"] == "https://example.sentry.io/issues/?project=1"
    assert links["Stripe"] == "https://dashboard.stripe.com/test/payments"
    assert (
        'href="http://localhost:5555" target="_blank" rel="noopener"' in response.content.decode()
    )
    # Every page of the project in the list opens for the superuser.
    # Not /sentry-debug/: it fails on purpose (its own tests in test_sentry.py)
    internal = [
        url for url in links.values() if url.startswith("/") and url != reverse("sentry_debug")
    ]
    assert len(internal) == 8  # admin x3, API x4, health
    for url in internal:
        assert superuser_client.get(url).status_code == 200, url


# Generated with AI
def test_services_that_are_not_set_up_have_no_link(superuser_client, settings):
    settings.FLOWER_URL = ""  # Railway: no Flower
    settings.SENTRY_ISSUES_URL = ""
    settings.STRIPE_SECRET_KEY = ""

    links = tool_links(superuser_client.get(reverse("users:profile")))

    assert "Flower" not in links
    assert "Sentry" not in links
    assert "Stripe" not in links


# Generated with AI
@pytest.mark.parametrize("client_fixture", ["customer_client", "manager_client"])
def test_tools_are_only_for_the_superuser(client_fixture, request):
    response = request.getfixturevalue(client_fixture).get(reverse("users:profile"))

    assert "tool_groups" not in response.context
    assert "Flower" not in response.content.decode()


def test_staff_profile_links_to_the_admin(manager_client, customer_client):
    """The navbar has no admin link: a manager (staff, not a superuser, so
    without the Tools block) opens the admin from the profile "Status" line."""
    admin_link = f'<a href="{reverse("admin:index")}">'

    assert admin_link in manager_client.get(reverse("users:profile")).content.decode()
    assert admin_link not in customer_client.get(reverse("users:profile")).content.decode()


# ---------------------------------------------------------------------------
# Navbar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url_name", "active_link"),
    [("books:list", "books:list"), ("books:author_list", "books:author_list")],
)
def test_navbar_brand_menu_highlights_the_current_page(client, url_name, active_link):
    html = client.get(reverse(url_name)).content.decode()

    assert 'class="navbar-brand fw-semibold dropdown-toggle"' in html
    # Whitespace between the attributes doesn't matter, only their order
    active = rf'class="dropdown-item active"\s+aria-current="page"\s+href="{reverse(active_link)}"'
    assert re.search(active, html)


def test_navbar_has_no_admin_link_even_for_superuser(superuser_client):
    html = superuser_client.get(reverse("books:list")).content.decode()
    navbar = html[html.index('<nav class="navbar') : html.index("</nav>")]

    assert reverse("admin:index") not in navbar


# Generated with AI
def test_every_page_loads_the_theme_script_before_the_page_is_drawn(client):
    """static/js/theme.js sets data-bs-theme in <head>: without defer / async,
    otherwise a dark page flashes white on every click."""
    html = client.get(reverse("books:list")).content.decode()
    head = html[: html.index("</head>")]

    assert re.search(r'<script src="[^"]*js/theme\.js"></script>', head)


def test_navbar_has_theme_switcher_with_three_choices(client):
    html = client.get(reverse("books:list")).content.decode()

    assert "data-theme-switcher" in html
    for choice in ("light", "dark", "auto"):
        assert f'data-theme-value="{choice}"' in html
