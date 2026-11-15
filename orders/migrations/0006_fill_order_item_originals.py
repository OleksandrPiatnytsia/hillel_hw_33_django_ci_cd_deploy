"""The items of the orders made before the currencies: nothing was converted.

Every order then was in UAH (0005 gave them currency=UAH, exchange_rate=1),
and so were the books. So the original price of an item is its price, the
original currency is the order currency, and the rate is 1. After this the
three fields are made NOT NULL (0007).
"""

from decimal import Decimal

from django.db import migrations
from django.db.models import F, OuterRef, Subquery


def fill_originals(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    # One UPDATE for all the items; the currency of the order is read by a
    # subquery (an UPDATE can't JOIN another table in the Django ORM)
    OrderItem.objects.filter(original_price__isnull=True).update(
        original_price=F("price"),
        original_currency_id=Subquery(
            Order.objects.filter(pk=OuterRef("order_id")).values("currency_id")[:1]
        ),
        exchange_rate=Decimal("1"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0005_order_currency_order_exchange_rate_and_more"),
    ]

    # Back: nothing to undo, 0005 removes the columns
    operations = [migrations.RunPython(fill_originals, migrations.RunPython.noop)]
