"""Book formats, stage 3: the cart, the checkout and the orders by format.

A line of the cart and of an order is a FORMAT of a book (paper, e-book,
audiobook) with its own price. Only the paper book has copies in the
warehouse: it is limited, reserved and returned; a file is always
available.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from books.models import Book, BookFormat
from cart.cart import CART_SESSION_KEY
from inventory.models import Stock
from orders.models import OrderItem
from orders.reports import build_daily_report
from orders.services import OrderError, cancel_order, create_order

from ..factories import BookFactory, BookFormatFactory, OrderFactory, UserFactory
from ..helpers import format_id, format_row, formats_data, message_levels

pytestmark = pytest.mark.django_db

DELIVERY = {"full_name": "Ann", "phone": "+380671234567", "address": "Kyiv"}


def _two_formats(stock=5, paper="450.00", ebook="199.00"):
    """A book with paper (with `stock` copies) and an e-book on sale."""
    book = BookFactory(title="Тигролови", price=Decimal(paper), stock=stock)
    BookFormatFactory(book=book, format_type="ebook", price=Decimal(ebook))
    return book, book.formats.get(format_type="paper"), book.formats.get(format_type="ebook")


def _stock(book_format):
    return Stock.objects.get(format=book_format).quantity


# ---------------------------------------------------------------------------
# Availability: a file never runs out
# ---------------------------------------------------------------------------


# Generated with AI
def test_book_with_sold_out_paper_and_an_ebook_is_available():
    book, _paper, _ebook = _two_formats(stock=0)
    paper_only = BookFactory(stock=0)
    not_on_sale = BookFactory(formats=False)

    available = dict(Book.objects.with_availability().values_list("pk", "available"))

    assert available == {book.pk: True, paper_only.pk: False, not_on_sale.pk: False}
    # The property without the annotation says the same
    assert (
        Book.objects.get(pk=book.pk).available,
        Book.objects.get(pk=paper_only.pk).available,
    ) == (
        True,
        False,
    )


# Generated with AI
def test_stock_filter_counts_an_ebook_as_in_stock_and_low_only_for_paper():
    with_ebook, _paper, _ebook = _two_formats(stock=0)
    low = BookFactory(stock=2)
    out = BookFactory(stock=0)

    def titles(status):
        return {book.pk for book in Book.objects.by_stock_status(status)}

    assert titles("in_stock") == {with_ebook.pk, low.pk}
    assert titles("low") == {low.pk}
    assert titles("out") == {out.pk}


# Generated with AI
def test_main_format_is_the_first_that_can_be_bought():
    book, paper, ebook = _two_formats(stock=3)
    assert book.main_format == paper

    Stock.objects.filter(format=paper).update(quantity=0)
    book.refresh_from_db()
    assert book.main_format == ebook


# ---------------------------------------------------------------------------
# The catalog card and the book page
# ---------------------------------------------------------------------------


# Generated with AI
def test_catalog_keeps_a_book_with_an_ebook_among_the_available_ones(client):
    """ "Out of stock last": a sold out paper book with an e-book on sale is not last."""
    BookFactory(title="А paper only, sold out", stock=0)
    _two_formats(stock=0)  # «Тигролови»

    response = client.get(reverse("books:list"))

    titles = [book.title for book in response.context["books"]]
    assert titles == ["Тигролови", "А paper only, sold out"]


# Generated with AI
def test_book_page_disables_a_sold_out_paper_tile_and_chooses_the_ebook(client):
    book, paper, ebook = _two_formats(stock=0)

    content = client.get(book.get_absolute_url()).content.decode()

    tile = content.split(f'id="format-{paper.pk}"')[1].split(">")[0]
    assert "disabled" in tile and "checked" not in tile
    assert "checked" in content.split(f'id="format-{ebook.pk}"')[1].split(">")[0]
    assert "Немає в наявності" in content
    # The quantity and the button: an e-book can be bought
    assert 'name="quantity"' in content


# Generated with AI
def test_book_page_lists_the_formats_in_the_cart(client):
    book, paper, ebook = _two_formats()
    url = reverse("cart:add", args=[book.pk])
    client.post(url, {"quantity": 2, "format": paper.pk})
    client.post(url, {"quantity": 1, "format": ebook.pk})

    response = client.get(book.get_absolute_url())

    assert response.context["in_cart"] == [(paper, 2), (ebook, 1)]
    assert "Паперова — 2, Електронна — 1" in response.content.decode()


# ---------------------------------------------------------------------------
# The cart views
# ---------------------------------------------------------------------------


# Generated with AI
def test_add_to_cart_puts_the_chosen_format(client):
    book, _paper, ebook = _two_formats()

    response = client.post(reverse("cart:add", args=[book.pk]), {"quantity": 3, "format": ebook.pk})

    assert message_levels(response) == ["success"]
    assert client.session[CART_SESSION_KEY] == {str(ebook.pk): {"quantity": 3}}


# Generated with AI
def test_add_to_cart_without_a_format_takes_the_main_one(client):
    book, _paper, ebook = _two_formats(stock=0)

    client.post(reverse("cart:add", args=[book.pk]), {"quantity": 1})

    assert client.session[CART_SESSION_KEY] == {str(ebook.pk): {"quantity": 1}}


# Generated with AI
def test_add_to_cart_refuses_a_format_of_another_book(client):
    book, _paper, _ebook = _two_formats()
    other = BookFactory()

    response = client.post(
        reverse("cart:add", args=[book.pk]), {"quantity": 1, "format": format_id(other)}
    )

    assert response.status_code == 404
    assert not client.session.get(CART_SESSION_KEY)


# Generated with AI
def test_add_to_cart_refuses_a_format_not_on_sale_and_a_book_without_formats(client):
    book, _paper, ebook = _two_formats()
    BookFormat.objects.filter(pk=ebook.pk).update(is_active=False)
    nothing = BookFactory(formats=False)

    refused = client.post(reverse("cart:add", args=[book.pk]), {"quantity": 1, "format": ebook.pk})
    no_format = client.post(reverse("cart:add", args=[nothing.pk]), {"quantity": 1})

    assert message_levels(refused) == ["error"]
    assert message_levels(no_format)[-1] == "error"
    assert not client.session.get(CART_SESSION_KEY)


# Generated with AI
def test_cart_page_offers_the_other_formats_of_the_book(client):
    book, paper, ebook = _two_formats()
    client.post(reverse("cart:add", args=[book.pk]), {"quantity": 1, "format": paper.pk})

    content = client.get(reverse("cart:detail")).content.decode()

    assert reverse("cart:change_format", args=[paper.pk]) in content
    assert "Паперова — 450,00 ₴" in content and "Електронна — 199,00 ₴" in content
    assert 'value="{}" selected'.format(paper.pk) in content


# Generated with AI
def test_change_format_in_the_cart(client):
    book, paper, ebook = _two_formats()
    client.post(reverse("cart:add", args=[book.pk]), {"quantity": 2, "format": paper.pk})

    response = client.post(reverse("cart:change_format", args=[paper.pk]), {"format": ebook.pk})

    assert message_levels(response)[-1] == "success"
    assert client.session[CART_SESSION_KEY] == {str(ebook.pk): {"quantity": 2}}


# Generated with AI
def test_change_format_to_another_book_is_404_and_get_is_405(client):
    book, paper, _ebook = _two_formats()
    client.post(reverse("cart:add", args=[book.pk]), {"quantity": 1, "format": paper.pk})
    url = reverse("cart:change_format", args=[paper.pk])

    assert client.post(url, {"format": format_id(BookFactory())}).status_code == 404
    assert client.get(url).status_code == 405
    assert client.session[CART_SESSION_KEY] == {str(paper.pk): {"quantity": 1}}


# Generated with AI
def test_remove_one_format_keeps_the_other(client):
    book, paper, ebook = _two_formats()
    url = reverse("cart:add", args=[book.pk])
    client.post(url, {"quantity": 1, "format": paper.pk})
    client.post(url, {"quantity": 1, "format": ebook.pk})

    client.post(reverse("cart:remove", args=[paper.pk]))

    assert client.session[CART_SESSION_KEY] == {str(ebook.pk): {"quantity": 1}}


# ---------------------------------------------------------------------------
# create_order() / cancel_order()
# ---------------------------------------------------------------------------


# Generated with AI
def test_order_of_two_formats_of_one_book_reserves_only_paper():
    book, paper, ebook = _two_formats(stock=5)

    order = create_order(UserFactory(), {paper.pk: 2, ebook.pk: 3}, **DELIVERY)

    items = {item.format_type: item for item in order.items.all()}
    assert (items["paper"].format, items["paper"].price, items["paper"].quantity) == (
        paper,
        Decimal("450.00"),
        2,
    )
    assert (items["ebook"].format, items["ebook"].price, items["ebook"].book) == (
        ebook,
        Decimal("199.00"),
        book,
    )
    assert order.total == Decimal("1497.00")  # 2 * 450 + 3 * 199
    assert _stock(paper) == 3


# Generated with AI
def test_ebook_is_sold_with_paper_sold_out():
    _book, paper, ebook = _two_formats(stock=0)

    order = create_order(UserFactory(), {ebook.pk: 1}, **DELIVERY)

    assert order.items.get().format == ebook
    assert _stock(paper) == 0


# Generated with AI
def test_format_switched_off_can_not_be_ordered():
    _book, _paper, ebook = _two_formats()
    BookFormat.objects.filter(pk=ebook.pk).update(is_active=False)

    with pytest.raises(OrderError, match="більше не продається"):
        create_order(UserFactory(), {ebook.pk: 1}, **DELIVERY)


# Generated with AI
def test_cancel_returns_only_the_paper_copies():
    _book, paper, ebook = _two_formats(stock=5)
    order = create_order(UserFactory(), {paper.pk: 2, ebook.pk: 1}, **DELIVERY)

    cancel_order(order.pk)

    assert _stock(paper) == 5
    assert not Stock.objects.filter(format=ebook).exists()


# Generated with AI
def test_order_item_keeps_the_format_type_and_shows_it():
    _book, _paper, ebook = _two_formats()
    order = create_order(UserFactory(), {ebook.pk: 1}, **DELIVERY)
    # The format changed later: the order still says what was bought
    BookFormat.objects.filter(pk=ebook.pk).update(format_type="audiobook")

    item = OrderItem.objects.get(order=order)
    assert item.format_type == "ebook"
    assert item.display_title == "Тигролови (Електронна)"


# Generated with AI
def test_order_page_shows_the_format(customer_client, customer):
    _book, paper, ebook = _two_formats()
    order = OrderFactory(user=customer, items=[(paper, 1), (ebook, 2)])

    content = customer_client.get(order.get_absolute_url()).content.decode()

    assert "Тигролови (Паперова)" in content and "Тигролови (Електронна)" in content


# Generated with AI
def test_checkout_of_a_cart_with_two_formats(
    customer_client, mailoutbox, django_capture_on_commit_callbacks
):
    book, paper, ebook = _two_formats(stock=5)
    url = reverse("cart:add", args=[book.pk])
    customer_client.post(url, {"quantity": 1, "format": paper.pk})
    customer_client.post(url, {"quantity": 2, "format": ebook.pk})

    with django_capture_on_commit_callbacks(execute=True):
        response = customer_client.post(reverse("orders:checkout"), {**DELIVERY, "currency": "UAH"})

    order = response.wsgi_request.user.orders.get()
    assert {(item.format_type, item.quantity) for item in order.items.all()} == {
        ("paper", 1),
        ("ebook", 2),
    }
    assert _stock(paper) == 4
    assert not customer_client.session.get(CART_SESSION_KEY)
    assert "Тигролови (Електронна): 2 x 199,00 ₴ = 398,00 ₴" in mailoutbox[0].body


# ---------------------------------------------------------------------------
# The book form: an ordered format can't be removed
# ---------------------------------------------------------------------------


# Generated with AI
def test_book_form_refuses_to_remove_an_ordered_format(manager_client):
    book, paper, ebook = _two_formats()
    OrderFactory(items=[(ebook, 1)])

    response = manager_client.post(
        reverse("books:update", args=[book.pk]),
        {
            "title": book.title,
            "author": book.author.pk,
            "description": "",
            **formats_data(
                format_row(id=paper.pk, price="450.00"),
                format_row("ebook", id=ebook.pk, price="199.00", DELETE="on"),
                initial=2,
            ),
        },
    )

    assert response.status_code == 200
    assert "є в замовленнях" in response.content.decode()
    assert BookFormat.objects.filter(pk=ebook.pk).exists()


# ---------------------------------------------------------------------------
# The daily report and the API
# ---------------------------------------------------------------------------


# Generated with AI
def test_low_stock_report_lists_only_books_sold_on_paper():
    low = BookFactory(stock=1)
    BookFactory(format_type="ebook", formats=True)  # no copies at all: not "low"

    report = build_daily_report(OrderFactory().created_at.date())

    assert [book.pk for book in report.low_stock] == [low.pk]


# Generated with AI
def test_api_order_of_a_book_with_several_formats_needs_format_id(client, customer):
    # The bridge of stage 3 (book_id -> main format) is gone: with two
    # formats on sale the API doesn't choose for the client
    _book, paper, _ebook = _two_formats(stock=0)
    client.force_login(customer)

    response = client.post(
        "/api/orders/",
        {**DELIVERY, "items": [{"book_id": paper.book_id, "quantity": 1}]},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert not OrderItem.objects.exists()


# Generated with AI
def test_api_order_of_a_book_not_on_sale_is_400(client, customer):
    book = BookFactory(formats=False)
    client.force_login(customer)

    response = client.post(
        "/api/orders/",
        {**DELIVERY, "items": [{"book_id": book.pk, "quantity": 1}]},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "items" in response.json()


# ---------------------------------------------------------------------------
# Small paths
# ---------------------------------------------------------------------------


# Generated with AI
def test_change_format_without_a_format_or_to_the_same_one_changes_nothing(client):
    book, paper, _ebook = _two_formats()
    client.post(reverse("cart:add", args=[book.pk]), {"quantity": 2, "format": paper.pk})
    url = reverse("cart:change_format", args=[paper.pk])

    client.post(url, {"format": "paper"})
    client.post(url, {"format": paper.pk})

    assert client.session[CART_SESSION_KEY] == {str(paper.pk): {"quantity": 2}}


# Generated with AI
def test_format_deleted_after_it_was_put_into_the_cart_is_reported():
    book = BookFactory()
    gone = format_id(book)
    book.delete()

    with pytest.raises(OrderError, match="більше немає в продажу"):
        create_order(UserFactory(), {gone: 1}, **DELIVERY)


# Generated with AI
def test_admin_format_list_shows_the_copies_of_paper_and_a_dash_for_a_file(manager_client):
    _book, _paper, _ebook = _two_formats(stock=4)

    response = manager_client.get(reverse("admin:books_bookformat_changelist"))

    stocks = [
        response.context["cl"].model_admin.stock(row) for row in response.context["cl"].result_list
    ]
    assert stocks == [4, "—"]


# Generated with AI
def test_availability_twice_and_a_format_read_again():
    book, paper, _ebook = _two_formats(stock=1)
    books = Book.objects.with_availability().with_availability()
    assert books.get(pk=book.pk).available is True

    assert paper.stock == 1
    Stock.objects.filter(format=paper).update(quantity=8)
    paper.refresh_from_db()
    assert paper.stock == 8
