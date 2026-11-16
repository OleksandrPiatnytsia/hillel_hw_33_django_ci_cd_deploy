from django.db.models.signals import post_save
from django.dispatch import receiver

from books.models import BookFormat

from .models import Stock, Warehouse


@receiver(post_save, sender=BookFormat)
def create_stock_row(sender, instance, created, raw=False, **kwargs):
    """Every paper format gets a row in the default warehouse, quantity 0.

    So the stock of a paper book is always a row that can be locked and
    changed (orders.services, the admin), never "no row = 0".
    Not only for a new format: a format changed to "paper" gets its row too
    (get_or_create keeps an existing one). An e-book or an audiobook has
    no copies, no row.
    raw=True: loaddata of a fixture; the fixture brings its own Stock rows.
    """
    if raw or not instance.is_paper:
        return
    Stock.objects.get_or_create(format=instance, warehouse=Warehouse.objects.get_default())
