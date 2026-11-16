from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from books.models import Author, Book, BookFormat, Category, Publisher
from currencies.models import BASE_CURRENCY
from inventory.services import set_stock

# slug -> name
CATEGORIES = {
    "fentezi": "Фентезі",
    "prigodi": "Пригоди",
    "roman": "Роман",
    "detektyv": "Детектив",
    "naukova-fantastyka": "Наукова фантастика",
}

# title, author, price, stock, description, category slugs.
# The price is in UAH; "8.50 EUR" is a price in another currency (a few
# books, so the catalog shows conversion from different currencies).
BOOKS = [
    ("Хоббіт", "Дж.Р. Толкін", "99.75", 3437, "Пригоди Більбо Торбина.", ["fentezi", "prigodi"]),
    (
        "Володар перснів",
        "Дж.Р. Толкін",
        "650.00",
        12,
        "Епічна сага про Середзем'я.",
        ["fentezi", "prigodi"],
    ),
    (
        "Гра престолів",
        "Джордж Мартін",
        "8.50 EUR",
        4,
        "Перша книга циклу «Пісня льоду й полум'я».",
        ["fentezi", "roman"],
    ),
    ("Відьмак. Останнє бажання", "Анджей Сапковський", "280.00", 0, "", ["fentezi"]),
    (
        "Дюна",
        "Френк Герберт",
        "390.00",
        7,
        "Класика наукової фантастики.",
        ["naukova-fantastyka", "roman"],
    ),
    (
        "Марсіянин",
        "Енді Вейр",
        "250.00",
        25,
        "Виживання на Марсі.",
        ["naukova-fantastyka", "prigodi"],
    ),
    ("Таємне життя дерев", "Петер Вольлебен", "4.50 USD", 2, "", []),
    (
        "Вбивство в «Східному експресі»",
        "Агата Крісті",
        "140.00",
        30,
        "Пуаро розслідує вбивство в потязі.",
        ["detektyv"],
    ),
    (
        "Собака Баскервілів",
        "Артур Конан Дойл",
        "120.00",
        0,
        "Шерлок Холмс і родове прокляття.",
        ["detektyv", "prigodi"],
    ),
    ("Воно", "Стівен Кінг", "11.00 USD", 5, "Жах у містечку Деррі.", ["roman"]),
    ("Сяйво", "Стівен Кінг", "360.00", 15, "", ["roman"]),
    (
        "Тигролови",
        "Іван Багряний",
        "200.00",
        9,
        "Втеча з ешелону на Далекому Сході.",
        ["prigodi", "roman"],
    ),
]

PAPER, EBOOK, AUDIOBOOK = Book.BookType.PAPER, Book.BookType.EBOOK, Book.BookType.AUDIOBOOK
HARD, SOFT, JACKET = Book.CoverType.HARD, Book.CoverType.SOFT, Book.CoverType.DUST_JACKET

# The details of the edition, by title: publisher, type, cover, language,
# year, pages. Sample values for the catalog filters (different
# publishers, types, languages and years), not the exact real editions.
# None / "" = not known: "Воно" has no publisher, the e-books and the
# audiobook have no cover.
DETAILS = {
    "Хоббіт": ("Видавництво Старого Лева", PAPER, HARD, "uk", 2019, 304),
    "Володар перснів": ("Vivat", PAPER, JACKET, "uk", 2021, 1216),
    "Гра престолів": ("Клуб Сімейного Дозвілля", PAPER, HARD, "uk", 2018, 800),
    "Відьмак. Останнє бажання": ("Клуб Сімейного Дозвілля", EBOOK, "", "uk", 2020, 320),
    "Дюна": ("Клуб Сімейного Дозвілля", PAPER, HARD, "uk", 2019, 592),
    "Марсіянин": ("Наш Формат", PAPER, SOFT, "uk", 2021, 384),
    "Таємне життя дерев": ("Наш Формат", AUDIOBOOK, "", "uk", 2018, None),
    "Вбивство в «Східному експресі»": ("Клуб Сімейного Дозвілля", PAPER, SOFT, "uk", 2020, 256),
    "Собака Баскервілів": ("Фоліо", PAPER, HARD, "uk", 2017, 224),
    "Воно": (None, PAPER, SOFT, "en", 2019, 1184),
    "Сяйво": ("Клуб Сімейного Дозвілля", PAPER, HARD, "uk", 2016, 448),
    "Тигролови": ("Фоліо", EBOOK, "", "uk", 2022, None),
}


class Command(BaseCommand):
    help = "Fill the database with sample categories and books (safe to re-run)."

    @transaction.atomic
    def handle(self, *args, **options):
        categories = {}
        for slug, name in CATEGORIES.items():
            category, created = Category.objects.get_or_create(slug=slug, defaults={"name": name})
            categories[slug] = category
            if created:
                self.stdout.write(f"+ category {name}")

        for title, author_name, price_text, stock, description, slugs in BOOKS:
            # "650.00" -> 650.00 UAH, "8.50 EUR" -> 8.50 EUR
            price, _, currency = price_text.partition(" ")
            author, _ = Author.objects.get_or_create(name=author_name)
            book, created = Book.objects.get_or_create(
                title=title,
                author=author,
                defaults={
                    "price": Decimal(price),
                    "currency_id": currency or BASE_CURRENCY,
                    "description": description,
                },
            )
            if created:
                self._fill_details(book, DETAILS.get(title))
            if created:
                # Only for a new book: re-running doesn't reset the stock
                # that orders have changed since. The row with 0 is already
                # there (inventory.signals); this sets the real number.
                set_stock(book, stock)
            # add() skips links that already exist, so re-running is safe
            book.categories.add(*(categories[slug] for slug in slugs))
            if created:
                self.stdout.write(f"+ book {book}")
            elif self._fill_details(book, DETAILS.get(title)):
                self.stdout.write(f"+ details of {book}")
            if self._add_format(book):
                self.stdout.write(f"+ format of {book}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {Category.objects.count()} categories, "
                f"{Author.objects.count()} authors, "
                f"{Book.objects.count()} books."
            )
        )

    def _add_format(self, book):
        """One format for a book that has none, from the book's own fields.

        The same values as the data migration books.0014 gives the books
        that existed before the formats: a new database (migrations first,
        then seed_books) gets its demo books with formats too. A book that
        already has a format keeps it. True if a format was created.
        """
        if book.formats.exists():
            return False
        paper = book.book_type == BookFormat.FormatType.PAPER
        book.formats.create(
            format_type=book.book_type,
            price=book.price,
            currency_id=book.currency_id,
            cover_type=book.cover_type if paper else "",
            pages=None if book.book_type == BookFormat.FormatType.AUDIOBOOK else book.pages,
        )
        return True

    def _fill_details(self, book, details):
        """Fill the details of the edition that the book doesn't have yet.

        Only the empty fields: a book seeded before these fields gets them
        on a re-run, but what a manager has typed in stays. The type is
        "paper" by default, so it is set only together with the other
        details (a book without any of them). True if something changed.
        """
        if details is None:
            return False
        publisher_name, book_type, cover_type, language, year, pages = details
        publisher = None
        if publisher_name:
            # get_or_create: the list comes from the migration books.0012,
            # but a name missing there must not stop the command
            publisher, _ = Publisher.objects.get_or_create(name=publisher_name)
        has_details = any(
            [book.publisher_id, book.cover_type, book.language, book.publication_year, book.pages]
        )
        values = {
            "publisher": publisher,
            "cover_type": cover_type,
            "language": language,
            "publication_year": year,
            "pages": pages,
        }
        if not has_details:
            values["book_type"] = book_type
        changed = []
        for field, value in values.items():
            current = getattr(book, field)
            # The type always has a value: compare it; the others: only empty ones
            needed = current != value if field == "book_type" else value and not current
            if needed:
                setattr(book, field, value)
                changed.append(field)
        if changed:
            # update_fields: only these columns (and the post_save signal
            # still drops the cache of the book)
            book.save(update_fields=[*changed, "updated_at"])
        return bool(changed)
