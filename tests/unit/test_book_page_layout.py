"""The layout of the book page (books/book_detail.html).

Right of the cover: the title, the author, a reserved row for the rating
and the wishlist, the categories and the description under the heading
"Опис"; a long description is cut by static/js/collapsible_text.js, the
page gives it the button "Читати повністю". The details ("Характеристики")
stay under the line, apart from the description.
"""

import re

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.urls import reverse

from ..factories import BookFactory, CategoryFactory

pytestmark = pytest.mark.django_db


def page(client, book, language="uk"):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    return client.get(reverse("books:detail", args=[book.pk])).content.decode()


def main_column(html):
    """The HTML of the column right of the cover (up to the format tiles)."""
    start = html.index('<div class="book-main">')
    return html[start : html.index('<div class="text-end">', start)]


# Generated with AI
def test_description_is_right_of_the_cover_under_its_heading(client):
    book = BookFactory(title="Kobzar", description="Перший рядок.\n\nДругий абзац.")

    column = main_column(page(client, book))

    assert "Kobzar" in column
    assert '<h2 class="book-section-title" id="book-description-title">Опис</h2>' in column
    assert "<p>Перший рядок.</p>" in column
    assert "<p>Другий абзац.</p>" in column
    # The description is in the column only, not under the line any more
    html = page(client, book)
    assert html.count("Перший рядок.") == 1


# Generated with AI
def test_description_comes_before_the_details_and_apart_from_them(client):
    book = BookFactory(description="Текст опису.", publication_year=2020)

    html = page(client, book)

    assert html.index("Текст опису.") < html.index("<hr>") < html.index("Характеристики")


# Generated with AI
def test_description_has_the_read_more_button_for_the_script(client):
    book = BookFactory(description="Довгий опис. " * 200)

    html = page(client, book)

    assert 'id="book-description" data-collapsible-text' in html
    button = re.search(r'<button class="[^"]*collapsible-toggle".*?</button>', html, re.S).group()
    # Hidden until the script sees that the text is longer than the cut
    assert " hidden" in button
    assert 'aria-controls="book-description"' in button
    assert 'aria-expanded="false"' in button
    assert 'data-label-more="Читати повністю"' in button
    assert 'data-label-less="Згорнути"' in button
    assert "js/collapsible_text" in html


# Generated with AI
def test_labels_in_english(client):
    book = BookFactory(description="Text.")

    html = page(client, book, language="en")

    assert ">Description</h2>" in html
    assert 'data-label-more="Read more"' in html
    assert 'data-label-less="Show less"' in html


# Generated with AI
def test_book_without_description_says_so_and_has_no_button(client):
    book = BookFactory(description="")

    column = main_column(page(client, book))

    assert ">Опис</h2>" in column
    assert "Опису поки немає." in column
    assert "collapsible-toggle" not in column


# Generated with AI
def test_reserved_row_for_rating_and_wishlist_is_between_author_and_categories(client):
    book = BookFactory(categories=[CategoryFactory(name="Поезія", slug="poetry")])

    column = main_column(page(client, book))

    meta = column.index('<div class="book-meta">')
    assert column.index(book.author.name) < meta < column.index("Поезія")
    assert '<div class="book-rating"></div>' in column
    assert '<div class="book-wishlist"></div>' in column


# Generated with AI
def test_description_fragment_is_cached_and_cleared_when_the_book_changes(client):
    book = BookFactory(description="Старий опис.")
    page(client, book)
    key = make_template_fragment_key("book_detail_description", [book.pk, "uk"])
    assert cache.get(key) is not None

    book.description = "Новий опис."
    book.save()

    assert cache.get(key) is None
    html = page(client, book)
    assert "Новий опис." in html
    assert "Старий опис." not in html
