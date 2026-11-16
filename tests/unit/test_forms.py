"""Unit tests of the forms: cleaning and validation, without views."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from books import forms as book_forms
from books.filters import CatalogFilter
from books.forms import BookForm
from cart.forms import CartAddForm
from orders.forms import CheckoutForm
from users.forms import ProfileForm, SignUpForm

from ..factories import AuthorFactory, UserFactory


def png_file(name="cover.png"):
    """A real 1x1 PNG: ImageField checks the file with Pillow."""
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def test_checkout_form_normalizes_name_and_phone():
    form = CheckoutForm(
        data={
            "full_name": "  Ann   Shevchenko ",
            "phone": "+380 (67) 123-45-67",
            "address": "Kyiv",
        }
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["full_name"] == "Ann Shevchenko"
    assert form.cleaned_data["phone"] == "+380671234567"
    assert form.cleaned_data["save_to_profile"] is False  # unchecked box = not sent


def test_checkout_form_rejects_wrong_phone_and_empty_address():
    form = CheckoutForm(data={"full_name": "Ann", "phone": "123", "address": ""})

    assert not form.is_valid()
    assert set(form.errors) == {"phone", "address"}


@pytest.mark.parametrize("quantity", ["0", "-1", "abc", ""])
def test_cart_add_form_rejects_wrong_quantity(quantity):
    assert not CartAddForm(data={"quantity": quantity}).is_valid()


@pytest.mark.django_db
def test_sign_up_form_rejects_email_of_another_user_in_other_case():
    UserFactory(email="ann@example.com")

    form = SignUpForm(
        data={
            "username": "ann2",
            "email": "ANN@Example.com",
            "password1": "Very-strong-pass-42",
            "password2": "Very-strong-pass-42",
        }
    )

    assert not form.is_valid()
    assert "email" in form.errors


@pytest.mark.django_db
def test_profile_form_saves_normalized_phone():
    user = UserFactory()
    form = ProfileForm(
        data={"first_name": "Ann", "last_name": "S", "phone": "067 123 45 67", "address": "Lviv"},
        instance=user,
    )

    assert form.is_valid(), form.errors
    form.save()
    user.refresh_from_db()
    assert user.phone == "0671234567"


@pytest.mark.django_db
def test_catalog_filter_form_price_from_greater_than_price_to_is_invalid():
    form = CatalogFilter(data={"price_min": "500", "price_max": "100"}).form

    assert not form.is_valid()
    assert "__all__" in form.errors  # an error of the whole form, from clean()


@pytest.mark.django_db
def test_book_form_has_no_stock_field():
    # The copies are changed in the admin, per warehouse (inventory.Stock)
    assert "stock" not in BookForm().fields


def _book_form_data():
    return {
        "title": "New book",
        "author": AuthorFactory().pk,
        "description": "",
    }


@pytest.mark.django_db
def test_book_form_accepts_png_cover():
    form = BookForm(data=_book_form_data(), files={"cover": png_file()})

    assert form.is_valid(), form.errors
    assert form.cleaned_data["cover"].name == "cover.png"


@pytest.mark.django_db
def test_book_form_rejects_cover_with_wrong_extension():
    # A real image, but .gif is not in COVER_ALLOWED_EXTENSIONS
    form = BookForm(data=_book_form_data(), files={"cover": png_file("cover.gif")})

    assert not form.is_valid()
    assert "cover" in form.errors


@pytest.mark.django_db
def test_book_form_rejects_too_large_cover(monkeypatch):
    # A 2 MB image file is slow to build; a 0 MB limit makes any file too large
    monkeypatch.setattr(book_forms, "COVER_MAX_SIZE_MB", 0)

    form = BookForm(data=_book_form_data(), files={"cover": png_file()})

    assert not form.is_valid()
    assert "cover" in form.errors
