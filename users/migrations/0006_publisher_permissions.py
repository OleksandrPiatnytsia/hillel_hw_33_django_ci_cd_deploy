"""Rights to the new model books.Publisher, the same way as to authors.

    Customers   view
    Editors     view, add, change    (like authors: no deleting)
    Managers    + delete

The groups come from users/0003_create_groups.py; that migration gave the
rights of the models that existed then, so a new model needs its own.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

# Kept here, not imported from app code: a migration must keep working
# the same way even if the app code changes later
VIEW = ["view_publisher"]
EDIT = ["add_publisher", "change_publisher"]
MANAGE = ["delete_publisher"]

GROUPS = {
    "Customers": VIEW,
    "Editors": VIEW + EDIT,
    "Managers": VIEW + EDIT + MANAGE,
}


def _permissions(apps, codenames):
    Permission = apps.get_model("auth", "Permission")
    permissions = Permission.objects.filter(content_type__app_label="books", codename__in=codenames)
    # Fail loudly on a typo instead of giving fewer rights
    missing = set(codenames) - set(permissions.values_list("codename", flat=True))
    if missing:
        raise RuntimeError(f"Unknown permissions: {sorted(missing)}")
    return permissions


def add_permissions(apps, schema_editor):
    # Permissions are normally created by the post_migrate signal — AFTER
    # all migrations. On a fresh database the Publisher ones don't exist
    # yet, so create them now (the same trick as in users/0003)
    books_config = apps.get_app_config("books")
    books_config.models_module = True  # create_permissions() skips apps without it
    create_permissions(books_config, apps=apps, verbosity=0)
    books_config.models_module = None

    Group = apps.get_model("auth", "Group")
    for name, codenames in GROUPS.items():
        # get_or_create: the groups come from users/0003, but don't depend on it
        group, _ = Group.objects.get_or_create(name=name)
        # add(), not set(): keep the rights the group already has
        group.permissions.add(*_permissions(apps, codenames))


def remove_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name, codenames in GROUPS.items():
        group = Group.objects.filter(name=name).first()
        if group is not None:
            group.permissions.remove(*_permissions(apps, codenames))


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0005_user_language"),
        ("books", "0011_publisher_book_details"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(add_permissions, remove_permissions),
    ]
