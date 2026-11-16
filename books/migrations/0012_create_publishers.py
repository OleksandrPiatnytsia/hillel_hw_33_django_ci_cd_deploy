"""The main Ukrainian publishers: the list to choose from in the book form.

Data, not schema: every database (local Docker, Railway, the tests) gets
the same list on "migrate", nobody has to type it in the admin. More
publishers are added in the admin (Books -> Publishers); a book without a
publisher is fine too.

The names as the publishers write them (their own Latin names stay
Latin: "Vivat", "ArtHuss").
"""

from django.db import migrations

# Kept here, not imported from app code: a migration must keep working
# the same way even if the app code changes later
PUBLISHERS = [
    "А-БА-БА-ГА-ЛА-МА-ГА",
    "Апріорі",
    "Артбукс",
    "Богдан",
    "Видавництво 21",
    "Видавництво Анетти Антоненко",
    "Видавництво Жупанського",
    "Видавництво Старого Лева",
    "Віхола",
    "Жорж",
    "Знання",
    "Клуб Сімейного Дозвілля",
    "Книголав",
    "Комора",
    "Лабораторія",
    "Наш Формат",
    "Основи",
    "Ранок",
    "Рідна мова",
    "Темпора",
    "Фабула",
    "Фоліо",
    "Час Майстрів",
    "Читаріум",
    "Ще одну сторінку",
    "ArtHuss",
    "BookChef",
    "Discursus",
    "Meridian Czernowitz",
    "Nebo BookLab Publishing",
    "Vivat",
    "Yakaboo Publishing",
]


def create_publishers(apps, schema_editor):
    Publisher = apps.get_model("books", "Publisher")
    for name in PUBLISHERS:
        # get_or_create: a publisher added by hand before this migration
        # (or a second run) is not duplicated
        Publisher.objects.get_or_create(name=name)


def delete_publishers(apps, schema_editor):
    # Back to 0011: only the publishers without books. A publisher with
    # books stays (PROTECT would stop the delete anyway); its books keep it
    Publisher = apps.get_model("books", "Publisher")
    Publisher.objects.filter(name__in=PUBLISHERS, books__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("books", "0011_publisher_book_details"),
    ]

    operations = [
        migrations.RunPython(create_publishers, delete_publishers),
    ]
