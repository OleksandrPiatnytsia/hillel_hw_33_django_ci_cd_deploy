"""The formats of the books in the API: /api/formats/, "formats" of a book, orders by format.

GET  /api/formats/?book=7          the formats of a book (on sale; all for editors)
POST /api/formats/                 a new format: book_id, format_type, price, ...
PATCH / PUT / DELETE /api/formats/<pk>/
POST /api/orders/ {"items": [{"format_id": 12, "quantity": 1}]}
"""

from decimal import Decimal

import pytest

from books.models import BookFormat
from orders.models import Order
from tests.factories import BookFactory, BookFormatFactory, OrderFactory

pytestmark = pytest.mark.django_db


def new_format_data(book, **changes):
    return {"book_id": book.pk, "format_type": "ebook", "price": "149.00", **changes}


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


# Generated with AI
def test_a_book_lists_its_formats_on_sale(api_client):
    book = BookFactory(title="Kobzar", price=Decimal("350.00"), cover_type="hard", stock=4)
    ebook = BookFormatFactory(book=book, format_type="ebook", price=Decimal("149.00"))
    BookFormatFactory(book=book, format_type="audiobook", is_active=False)

    data = api_client.get(f"/api/books/{book.pk}/").json()

    # Paper first; the turned off audiobook is not sold, so not listed
    assert [(f["format_type"], f["price"], f["stock"], f["in_stock"]) for f in data["formats"]] == [
        ("paper", "350.00", 4, True),
        # A file has no copies: null, not 0, and it is always available
        ("ebook", "149.00", None, True),
    ]
    assert data["formats"][1]["id"] == ebook.pk
    assert data["formats"][0]["format_type_display"] == "Паперова"
    assert "book_id" not in data["formats"][0]
    # The price "from": the cheapest format on sale
    assert data["display_price"] == "149.00"


# Generated with AI
def test_a_book_with_paper_sold_out_and_an_ebook_is_in_stock(api_client):
    book = BookFactory(stock=0)
    BookFormatFactory(book=book, format_type="ebook")

    assert api_client.get(f"/api/books/{book.pk}/").json()["in_stock"] is True


# Generated with AI
def test_formats_of_one_book_turned_off_ones_only_for_editors(api_client, as_user, editor):
    book = BookFactory()
    BookFormatFactory(book=book, format_type="ebook", is_active=False)
    BookFactory()  # another book: not in ?book=

    anonymous = api_client.get("/api/formats/", {"book": book.pk}).json()
    edited = as_user(editor).get("/api/formats/", {"book": book.pk}).json()

    assert [f["format_type"] for f in anonymous["results"]] == ["paper"]
    assert [(f["format_type"], f["is_active"]) for f in edited["results"]] == [
        ("paper", True),
        ("ebook", False),
    ]
    assert edited["results"][0]["book_id"] == book.pk


# Generated with AI
def test_books_filtered_and_sorted_by_the_cheapest_format_on_sale(api_client):
    cheap_ebook = BookFactory(title="Cheap e-book", price=Decimal("500.00"))
    BookFormatFactory(book=cheap_ebook, format_type="ebook", price=Decimal("100.00"))
    turned_off = BookFactory(title="Turned off", price=Decimal("300.00"))
    BookFormatFactory(book=turned_off, format_type="ebook", price=Decimal("50.00"), is_active=False)

    cheap = api_client.get("/api/books/", {"price_max": "150"}).json()["results"]
    ordered = api_client.get("/api/books/", {"ordering": "price"}).json()["results"]

    # The turned off 50 UAH e-book doesn't count: "Turned off" costs 300
    assert [book["title"] for book in cheap] == ["Cheap e-book"]
    assert [(book["title"], book["display_price"]) for book in ordered] == [
        ("Cheap e-book", "100.00"),
        ("Turned off", "300.00"),
    ]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


# Generated with AI
def test_editor_adds_an_ebook_and_the_book_is_on_sale(as_user, editor):
    book = BookFactory(formats=False)

    response = as_user(editor).post("/api/formats/", new_format_data(book), format="json")

    assert response.status_code == 201, response.json()
    data = response.json()
    assert (data["book_id"], data["format_type"], data["price"]) == (book.pk, "ebook", "149.00")
    assert (data["stock"], data["in_stock"], data["is_active"]) == (None, True, True)
    answer = as_user(editor).get(f"/api/books/{book.pk}/").json()
    assert (answer["in_stock"], answer["display_price"]) == (True, "149.00")


# Generated with AI
@pytest.mark.parametrize("user, status", [(None, 401), ("customer", 403)])
def test_only_users_with_the_permission_write_formats(api_client, as_user, request, user, status):
    book = BookFactory(formats=False)
    client = as_user(request.getfixturevalue(user)) if user else api_client

    response = client.post("/api/formats/", new_format_data(book), format="json")

    assert response.status_code == status
    assert not BookFormat.objects.exists()


# Generated with AI
@pytest.mark.parametrize(
    "changes, field",
    [
        ({"cover_type": "hard"}, "cover_type"),  # an e-book has no cover
        ({"format_type": "audiobook", "pages": 300}, "pages"),
        ({"format_type": "paper"}, "format_type"),  # the book has paper already
        ({"price": "-1"}, "price"),
        ({"format_type": "vinyl"}, "format_type"),
        ({"book_id": 999999}, "book_id"),
    ],
)
def test_invalid_format_data_is_400(as_user, editor, changes, field):
    book = BookFactory()

    response = as_user(editor).post(
        "/api/formats/", new_format_data(book, **changes), format="json"
    )

    assert response.status_code == 400
    assert field in response.json()
    assert book.formats.count() == 1


# Generated with AI
def test_the_type_and_the_book_of_a_format_are_not_changed(as_user, editor):
    paper = BookFactory(cover_type="hard").formats.get()
    client = as_user(editor)

    other_type = client.patch(f"/api/formats/{paper.pk}/", {"format_type": "ebook"}, format="json")
    other_book = client.patch(
        f"/api/formats/{paper.pk}/", {"book_id": BookFactory().pk}, format="json"
    )
    # PUT with everything read before (the same type and book, the stock too)
    full = client.get(f"/api/formats/{paper.pk}/").json()
    put = client.put(f"/api/formats/{paper.pk}/", {**full, "price": "199.00"}, format="json")

    assert other_type.status_code == other_book.status_code == 400
    assert "format_type" in other_type.json() and "book_id" in other_book.json()
    assert put.status_code == 200, put.json()
    paper.refresh_from_db()
    assert (paper.format_type, paper.price) == ("paper", Decimal("199.00"))


# Generated with AI
def test_patch_checks_the_cover_with_the_current_type(as_user, editor):
    book = BookFactory()
    ebook = BookFormatFactory(book=book, format_type="ebook")

    response = as_user(editor).patch(
        f"/api/formats/{ebook.pk}/", {"cover_type": "soft"}, format="json"
    )

    assert response.status_code == 400
    assert "cover_type" in response.json()


# ---------------------------------------------------------------------------
# Stock: paper only, inventory.change_stock only
# ---------------------------------------------------------------------------


# Generated with AI
def test_editor_cannot_change_the_stock(as_user, editor):
    paper = BookFactory(stock=10).formats.get()
    book = BookFactory(formats=False)
    client = as_user(editor)

    changed = client.patch(f"/api/formats/{paper.pk}/", {"stock": 99}, format="json")
    new = client.post(
        "/api/formats/", new_format_data(book, format_type="paper", stock=5), format="json"
    )
    same = client.patch(f"/api/formats/{paper.pk}/", {"stock": 10}, format="json")

    assert changed.status_code == new.status_code == 403
    assert same.status_code == 200
    assert paper.stocks.get().quantity == 10
    assert not book.formats.exists()


# Generated with AI
def test_manager_sets_the_stock_of_a_paper_format(as_user, manager):
    book = BookFactory(formats=False)
    client = as_user(manager)

    created = client.post(
        "/api/formats/", new_format_data(book, format_type="paper", stock=7), format="json"
    )
    changed = client.patch(f"/api/formats/{created.json()['id']}/", {"stock": 3}, format="json")

    assert (created.status_code, created.json()["stock"]) == (201, 7)
    assert (changed.status_code, changed.json()["stock"]) == (200, 3)
    book.refresh_from_db()
    assert book.stock == 3


# Generated with AI
def test_a_file_has_no_stock(as_user, manager):
    book = BookFactory(formats=False)
    ebook = BookFormatFactory(book=book, format_type="ebook")
    client = as_user(manager)

    new = client.post("/api/formats/", new_format_data(book, format_type="audiobook", stock=5))
    changed = client.patch(f"/api/formats/{ebook.pk}/", {"stock": 5}, format="json")
    sent_back = client.patch(f"/api/formats/{ebook.pk}/", {"stock": None}, format="json")

    assert new.status_code == changed.status_code == 400
    assert "stock" in new.json() and "stock" in changed.json()
    assert sent_back.status_code == 200


# ---------------------------------------------------------------------------
# Deleting
# ---------------------------------------------------------------------------


# Generated with AI
def test_deleting_a_format_leaves_the_others_and_the_price_from(as_user, editor):
    book = BookFactory(price=Decimal("350.00"))
    ebook = BookFormatFactory(book=book, format_type="ebook", price=Decimal("149.00"))

    response = as_user(editor).delete(f"/api/formats/{book.formats.get(format_type='paper').pk}/")

    assert response.status_code == 204
    assert list(book.formats.all()) == [ebook]
    answer = as_user(editor).get(f"/api/books/{book.pk}/").json()
    assert answer["display_price"] == "149.00"


# Generated with AI
def test_the_last_format_and_an_ordered_one_are_not_deleted(as_user, editor):
    last = BookFactory().formats.get()
    ordered_book = BookFactory()
    OrderFactory(items=[(ordered_book, 1)])
    BookFormatFactory(book=ordered_book, format_type="ebook")
    ordered = ordered_book.formats.get(format_type="paper")
    client = as_user(editor)

    first = client.delete(f"/api/formats/{last.pk}/")
    second = client.delete(f"/api/formats/{ordered.pk}/")

    assert first.status_code == second.status_code == 409
    assert BookFormat.objects.filter(pk__in=[last.pk, ordered.pk]).count() == 2


# ---------------------------------------------------------------------------
# Orders by format
# ---------------------------------------------------------------------------


def order_data(*lines, **changes):
    """lines: {"format_id": ..., "quantity": ...} or {"book_id": ...} dicts."""
    return {
        "full_name": "Ann Shevchenko",
        "phone": "+380671234567",
        "address": "Kyiv",
        "items": list(lines),
        **changes,
    }


@pytest.fixture
def book_with_two_formats():
    book = BookFactory(title="Kobzar", price=Decimal("350.00"), stock=5)
    BookFormatFactory(book=book, format_type="ebook", price=Decimal("149.00"))
    return book


# Generated with AI
def test_an_ebook_is_ordered_by_format_id_without_the_stock(
    as_user, customer, book_with_two_formats
):
    ebook = book_with_two_formats.formats.get(format_type="ebook")

    response = as_user(customer).post(
        "/api/orders/", order_data({"format_id": ebook.pk, "quantity": 2}), format="json"
    )

    assert response.status_code == 201, response.json()
    item = response.json()["items"][0]
    assert item["format"] == {
        "id": ebook.pk,
        "format_type": "ebook",
        "format_type_display": "Електронна",
    }
    assert (item["price"], response.json()["total"]) == ("149.00", "298.00")
    book_with_two_formats.refresh_from_db()
    assert book_with_two_formats.stock == 5  # a file reserves no copies


# Generated with AI
def test_book_id_of_a_book_with_several_formats_is_400(as_user, customer, book_with_two_formats):
    response = as_user(customer).post(
        "/api/orders/",
        order_data({"book_id": book_with_two_formats.pk, "quantity": 1}),
        format="json",
    )

    assert response.status_code == 400
    assert "format_id" in str(response.json()["items"])
    assert not Order.objects.exists()


# Generated with AI
def test_book_id_of_a_book_with_one_format_on_sale(as_user, customer, book_with_two_formats):
    book_with_two_formats.formats.filter(format_type="paper").update(is_active=False)

    response = as_user(customer).post(
        "/api/orders/",
        order_data({"book_id": book_with_two_formats.pk, "quantity": 1}),
        format="json",
    )

    assert response.status_code == 201, response.json()
    assert response.json()["items"][0]["format"]["format_type"] == "ebook"


# Generated with AI
@pytest.mark.parametrize(
    "line",
    [
        {"quantity": 1},  # neither
        "both",
        "turned off",
        "the same format twice",
    ],
)
def test_wrong_format_lines_are_400(as_user, customer, line):
    book = BookFactory()
    paper = book.formats.get()
    if line == "both":
        lines = [{"format_id": paper.pk, "book_id": book.pk, "quantity": 1}]
    elif line == "turned off":
        lines = [
            {
                "format_id": BookFormatFactory(book=book, format_type="ebook", is_active=False).pk,
                "quantity": 1,
            }
        ]
    elif line == "the same format twice":
        lines = [{"format_id": paper.pk, "quantity": 1}, {"book_id": book.pk, "quantity": 1}]
    else:
        lines = [line]

    response = as_user(customer).post("/api/orders/", order_data(*lines), format="json")

    assert response.status_code == 400
    assert "items" in response.json()
    assert not Order.objects.exists()


# Generated with AI
def test_idempotency_key_compares_formats(as_user, customer, book_with_two_formats):
    paper = book_with_two_formats.formats.get(format_type="paper")
    ebook = book_with_two_formats.formats.get(format_type="ebook")
    client = as_user(customer)
    headers = {"HTTP_IDEMPOTENCY_KEY": "key-1"}

    first = client.post(
        "/api/orders/", order_data({"format_id": paper.pk, "quantity": 1}), format="json", **headers
    )
    again = client.post(
        "/api/orders/", order_data({"format_id": paper.pk, "quantity": 1}), format="json", **headers
    )
    other = client.post(
        "/api/orders/", order_data({"format_id": ebook.pk, "quantity": 1}), format="json", **headers
    )

    assert first.status_code == again.status_code == 201
    assert again["Idempotent-Replayed"] == "true"
    assert again.json()["id"] == first.json()["id"]
    assert other.status_code == 422
    assert Order.objects.count() == 1


# Generated with AI
def test_a_book_id_request_is_recognised_after_its_format_changed(as_user, customer):
    # The first request ordered the paper book by book_id; then paper is
    # turned off and an e-book goes on sale. The retry names the same book:
    # the same request, the same order (not 422, not a second order)
    book = BookFactory()
    client = as_user(customer)
    headers = {"HTTP_IDEMPOTENCY_KEY": "key-2"}
    data = order_data({"book_id": book.pk, "quantity": 1})

    first = client.post("/api/orders/", data, format="json", **headers)
    book.formats.update(is_active=False)
    BookFormatFactory(book=book, format_type="ebook")
    again = client.post("/api/orders/", data, format="json", **headers)

    assert first.status_code == again.status_code == 201
    assert again.json()["id"] == first.json()["id"]
    assert again.json()["items"][0]["format"]["format_type"] == "paper"


# Generated with AI
def test_the_docs_describe_the_formats(api_client):
    schema = api_client.get("/api/schema/", {"format": "json"}).json()

    assert "/api/formats/" in schema["paths"]
    assert "format_id" in schema["components"]["schemas"]["OrderItemCreateRequest"]["properties"]
    assert "formats" in schema["components"]["schemas"]["Book"]["properties"]
