"""Rights to the new model books.BookFormat, the same way as to book categories.

    Customers   view
    Editors     view, add, change, delete
    Managers    view, add, change, delete

The formats are a part of the book form (like its categories): whoever may
edit a book may add, change and remove its formats. Deleting the book
itself stays a right of Managers.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

# Kept here, not imported from app code: a migration must keep working
# the same way even if the app code changes later
VIEW = ["view_bookformat"]
EDIT = ["add_bookformat", "change_bookformat", "delete_bookformat"]

GROUPS = {
    "Customers": VIEW,
    "Editors": VIEW + EDIT,
    "Managers": VIEW + EDIT,
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
    # all migrations. On a fresh database the BookFormat ones don't exist
    # yet, so create them now (the same trick as in users/0003 and 0006)
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
        ("users", "0006_publisher_permissions"),
        ("books", "0013_bookformat"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(add_permissions, remove_permissions),
    ]
