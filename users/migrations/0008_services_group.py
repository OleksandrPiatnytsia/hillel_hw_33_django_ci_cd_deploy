"""The group Services and the rights of the Analytics service.

    Services   orders.export_orders_for_analytics
               (the account "analytics-service" of Analytics: the backfill,
               GET /api/analytics/orders/)
    Managers   orders.view_sales_analytics (the page /analytics/)

The two permissions are declared in Order.Meta.permissions. They are made
here by name, not by create_permissions() like in users/0007: that one
reads them from the state of the orders migrations, and this migration
must not depend on the migration of orders that adds them (whichever of
the two runs first, the rows are the same; post_migrate finds them made).

The account itself is made by a command, not here: its password must not
be in the code (python manage.py create_service_account analytics-service).
"""

from django.db import migrations

# Kept here, not imported from app code: a migration must keep working
# the same way even if the app code changes later
PERMISSIONS = {
    "export_orders_for_analytics": "Can export orders to Analytics",
    "view_sales_analytics": "Can view the sales analytics",
}
GROUPS = {
    "Services": ["export_orders_for_analytics"],
    "Managers": ["view_sales_analytics"],
}


def _permissions(apps, codenames):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    order_type, _ = ContentType.objects.get_or_create(app_label="orders", model="order")
    return [
        Permission.objects.get_or_create(
            content_type=order_type,
            codename=codename,
            defaults={"name": PERMISSIONS[codename]},
        )[0]
        for codename in codenames
    ]


def add_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name, codenames in GROUPS.items():
        group, _ = Group.objects.get_or_create(name=name)
        # add(), not set(): keep the rights the group already has
        group.permissions.add(*_permissions(apps, codenames))


def remove_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name, codenames in GROUPS.items():
        group = Group.objects.filter(name=name).first()
        if group is not None:
            group.permissions.remove(*_permissions(apps, codenames))
    # The group made here goes away when nobody is in it; Managers stays
    Group.objects.filter(name="Services", user__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0007_bookformat_permissions"),
        ("orders", "0010_orderitem_format_required"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(add_permissions, remove_permissions),
    ]
