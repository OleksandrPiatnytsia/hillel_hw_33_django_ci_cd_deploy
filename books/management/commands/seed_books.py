from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from books.models import Author, Book, BookFormat, Category, Publisher
from currencies.models import BASE_CURRENCY
from inventory.services import paper_format_of, set_stock

# slug -> name
CATEGORIES = {
    "fentezi": "Фентезі",
    "prigodi": "Пригоди",
    "roman": "Роман",
    "detektyv": "Детектив",
    "naukova-fantastyka": "Наукова фантастика",
}

# title, author, stock of the paper book, description, category slugs.
# The prices are in FORMATS below.
BOOKS = [
    ("Хоббіт", "Дж.Р. Толкін", 3437, "Пригоди Більбо Торбина.", ["fentezi", "prigodi"]),
    ("Володар перснів", "Дж.Р. Толкін", 12, "Епічна сага про Середзем'я.", ["fentezi", "prigodi"]),
    (
        "Гра престолів",
        "Джордж Мартін",
        4,
        "Перша книга циклу «Пісня льоду й полум'я».",
        ["fentezi", "roman"],
    ),
    ("Відьмак. Останнє бажання", "Анджей Сапковський", 0, "", ["fentezi"]),
    ("Дюна", "Френк Герберт", 7, "Класика наукової фантастики.", ["naukova-fantastyka", "roman"]),
    ("Марсіянин", "Енді Вейр", 25, "Виживання на Марсі.", ["naukova-fantastyka", "prigodi"]),
    ("Таємне життя дерев", "Петер Вольлебен", 0, "", []),
    (
        "Вбивство в «Східному експресі»",
        "Агата Крісті",
        30,
        "Пуаро розслідує вбивство в потязі.",
        ["detektyv"],
    ),
    (
        "Собака Баскервілів",
        "Артур Конан Дойл",
        0,
        "Шерлок Холмс і родове прокляття.",
        ["detektyv", "prigodi"],
    ),
    ("Воно", "Стівен Кінг", 5, "Жах у містечку Деррі.", ["roman"]),
    ("Сяйво", "Стівен Кінг", 15, "", ["roman"]),
    ("Тигролови", "Іван Багряний", 9, "Втеча з ешелону на Далекому Сході.", ["prigodi", "roman"]),
]

# The details of the edition, by title: publisher, language, year.
# Sample values for the catalog filters, not the exact real editions.
# None = not known: "Воно" has no publisher.
DETAILS = {
    "Хоббіт": ("Видавництво Старого Лева", "uk", 2019),
    "Володар перснів": ("Vivat", "uk", 2021),
    "Гра престолів": ("Клуб Сімейного Дозвілля", "uk", 2018),
    "Відьмак. Останнє бажання": ("Клуб Сімейного Дозвілля", "uk", 2020),
    "Дюна": ("Клуб Сімейного Дозвілля", "uk", 2019),
    "Марсіянин": ("Наш Формат", "uk", 2021),
    "Таємне життя дерев": ("Наш Формат", "uk", 2018),
    "Вбивство в «Східному експресі»": ("Клуб Сімейного Дозвілля", "uk", 2020),
    "Собака Баскервілів": ("Фоліо", "uk", 2017),
    "Воно": (None, "en", 2019),
    "Сяйво": ("Клуб Сімейного Дозвілля", "uk", 2016),
    "Тигролови": ("Фоліо", "uk", 2022),
}

PAPER, EBOOK, AUDIOBOOK = (
    BookFormat.FormatType.PAPER,
    BookFormat.FormatType.EBOOK,
    BookFormat.FormatType.AUDIOBOOK,
)
HARD, SOFT, JACKET = (
    BookFormat.CoverType.HARD,
    BookFormat.CoverType.SOFT,
    BookFormat.CoverType.DUST_JACKET,
)

# The formats of every book: type, price, cover (paper only), pages (not
# for an audiobook). The price is in UAH; "8.50 EUR" is a price in another
# currency (a few formats, so the catalog shows the conversion). Some
# books in several formats (the tiles of the book page, the price "from"),
# some only as an e-book or an audiobook (always available, no stock).
FORMATS = {
    "Хоббіт": [
        (PAPER, "99.75", HARD, 304),
        (EBOOK, "79.00", "", 304),
        (AUDIOBOOK, "149.00", "", None),
    ],
    "Володар перснів": [(PAPER, "650.00", JACKET, 1216), (EBOOK, "299.00", "", 1216)],
    "Гра престолів": [(PAPER, "8.50 EUR", HARD, 800), (EBOOK, "5.00 USD", "", 800)],
    "Відьмак. Останнє бажання": [(EBOOK, "280.00", "", 320)],
    "Дюна": [(PAPER, "390.00", HARD, 592), (AUDIOBOOK, "249.00", "", None)],
    "Марсіянин": [(PAPER, "250.00", SOFT, 384)],
    "Таємне життя дерев": [(AUDIOBOOK, "4.50 USD", "", None)],
    "Вбивство в «Східному експресі»": [(PAPER, "140.00", SOFT, 256)],
    "Собака Баскервілів": [(PAPER, "120.00", HARD, 224)],
    "Воно": [(PAPER, "11.00 USD", SOFT, 1184)],
    "Сяйво": [(PAPER, "360.00", HARD, 448)],
    "Тигролови": [(EBOOK, "200.00", "", 288)],
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

        for title, author_name, stock, description, slugs in BOOKS:
            author, _ = Author.objects.get_or_create(name=author_name)
            book, created = Book.objects.get_or_create(
                title=title, author=author, defaults={"description": description}
            )
            # add() skips links that already exist, so re-running is safe
            book.categories.add(*(categories[slug] for slug in slugs))
            if created:
                self.stdout.write(f"+ book {book}")
            if self._fill_details(book, DETAILS[title]) and not created:
                self.stdout.write(f"+ details of {book}")
            if self._add_formats(book, FORMATS[title]):
                self.stdout.write(f"+ formats of {book}")
                # Only with the new formats: re-running doesn't reset the
                # stock that orders have changed since. The row with 0 is
                # already there (inventory.signals, made with the paper
                # format); this sets the real number. A file has no copies.
                if paper_format_of(book) is not None:
                    set_stock(book, stock)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {Category.objects.count()} categories, "
                f"{Author.objects.count()} authors, "
                f"{Book.objects.count()} books, "
                f"{BookFormat.objects.count()} formats."
            )
        )

    def _add_formats(self, book, formats):
        """The formats of FORMATS for a book that has none. True if they were created.

        A book that already has a format keeps its formats as they are: a
        manager may have changed a price, turned a format off or deleted it.
        """
        if book.formats.exists():
            return False
        for format_type, price_text, cover_type, pages in formats:
            # "650.00" -> 650.00 UAH, "8.50 EUR" -> 8.50 EUR
            price, _, currency = price_text.partition(" ")
            book.formats.create(
                format_type=format_type,
                price=Decimal(price),
                currency_id=currency or BASE_CURRENCY,
                cover_type=cover_type,
                pages=pages,
            )
        return True

    def _fill_details(self, book, details):
        """Fill the details of the edition that the book doesn't have yet.

        Only the empty fields: a book seeded before these fields gets them
        on a re-run, but what a manager has typed in stays. True if
        something changed.
        """
        publisher_name, language, year = details
        publisher = None
        if publisher_name:
            # get_or_create: the list comes from the migration books.0012,
            # but a name missing there must not stop the command
            publisher, _ = Publisher.objects.get_or_create(name=publisher_name)
        values = {"publisher": publisher, "language": language, "publication_year": year}
        changed = []
        for field, value in values.items():
            if value and not getattr(book, field):
                setattr(book, field, value)
                changed.append(field)
        if changed:
            # update_fields: only these columns (and the post_save signal
            # still drops the cache of the book)
            book.save(update_fields=[*changed, "updated_at"])
        return bool(changed)
