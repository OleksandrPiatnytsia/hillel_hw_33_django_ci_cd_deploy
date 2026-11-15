"""The three currencies of the shop: UAH (the base), USD, EUR.

Only the currencies, no rates: a rate is different every day. The first
rates come from the NBU: python manage.py update_exchange_rates (then
every day by Celery Beat). Until a currency has a rate it is not offered
on the site (services.available_currencies()).

More currencies are added in the admin; the NBU update loads the rate of
any active currency that the NBU publishes.
"""

from django.db import migrations

# Kept here, not imported from app code: a migration must keep working
# the same way even if the app code changes later
CURRENCIES = [
    # code, name, symbol
    ("UAH", "Ukrainian hryvnia", "₴"),
    ("USD", "US dollar", "$"),
    ("EUR", "Euro", "€"),
]


def create_currencies(apps, schema_editor):
    Currency = apps.get_model("currencies", "Currency")
    for code, name, symbol in CURRENCIES:
        # get_or_create: a second run (or a currency added by hand before
        # this migration) changes nothing
        Currency.objects.get_or_create(code=code, defaults={"name": name, "symbol": symbol})


def delete_currencies(apps, schema_editor):
    # Back to 0001 (migrate currencies 0001): without rates, otherwise the
    # PROTECT foreign key of ExchangeRate stops the delete, as it should
    Currency = apps.get_model("currencies", "Currency")
    Currency.objects.filter(code__in=[code for code, _name, _symbol in CURRENCIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("currencies", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_currencies, delete_currencies),
    ]
