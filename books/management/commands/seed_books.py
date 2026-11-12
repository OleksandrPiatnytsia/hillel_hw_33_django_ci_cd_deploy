from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from books.models import Author, Book, Category
from inventory.services import set_stock

# slug -> name
CATEGORIES = {
    "fentezi": "Фентезі",
    "prigodi": "Пригоди",
    "roman": "Роман",
    "detektyv": "Детектив",
    "naukova-fantastyka": "Наукова фантастика",
}

# title, author, price, stock, description, category slugs
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
        "420.00",
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
    ("Таємне життя дерев", "Петер Вольлебен", "180.00", 2, "", []),
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
    ("Воно", "Стівен Кінг", "480.00", 5, "Жах у містечку Деррі.", ["roman"]),
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

        for title, author_name, price, stock, description, slugs in BOOKS:
            author, _ = Author.objects.get_or_create(name=author_name)
            book, created = Book.objects.get_or_create(
                title=title,
                author=author,
                defaults={
                    "price": Decimal(price),
                    "description": description,
                },
            )
            if created:
                # Only for a new book: re-running doesn't reset the stock
                # that orders have changed since. The row with 0 is already
                # there (inventory.signals); this sets the real number.
                set_stock(book, stock)
            # add() skips links that already exist, so re-running is safe
            book.categories.add(*(categories[slug] for slug in slugs))
            if created:
                self.stdout.write(f"+ book {book}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {Category.objects.count()} categories, "
                f"{Author.objects.count()} authors, "
                f"{Book.objects.count()} books."
            )
        )
