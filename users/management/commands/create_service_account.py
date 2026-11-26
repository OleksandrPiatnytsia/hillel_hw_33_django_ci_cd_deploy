"""python manage.py create_service_account analytics-service

The account another service logs in with (JWT of /api/token/): a member
of the group Services, nothing else. Today the only one is "analytics-service"
of Analytics, it reads GET /api/analytics/orders/ (the backfill).

    python manage.py create_service_account analytics-service
        the password from the variable ANALYTICS_SERVICE_PASSWORD, or asked
        in the terminal when it is empty
    python manage.py create_service_account analytics-service --password-env MY_VAR

Safe to repeat: an existing account gets the new password and the group
again, and loses is_staff / is_superuser if somebody gave them. The same
password goes to BOOKSTORE_API_PASSWORD of Analytics.

Not is_staff: a service has no business in the admin. A service email in
the reserved domain .invalid: the field is required and unique, and no
email can ever be delivered there.
"""

import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

SERVICES_GROUP = "Services"
DEFAULT_PASSWORD_ENV = "ANALYTICS_SERVICE_PASSWORD"


class Command(BaseCommand):
    help = "Create or update an account of another service (group Services)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument(
            "--password-env",
            default=DEFAULT_PASSWORD_ENV,
            help=f"The variable with the password (default {DEFAULT_PASSWORD_ENV}).",
        )

    def handle(self, *args, username, password_env, **options):
        password = os.environ.get(password_env, "") or self.ask_password()
        group = Group.objects.filter(name=SERVICES_GROUP).first()
        if group is None:
            raise CommandError(f"No group {SERVICES_GROUP!r}: run python manage.py migrate first.")

        User = get_user_model()
        user = User.objects.filter(username=username).first() or User(
            username=username, email=f"{username}@services.invalid"
        )
        try:
            # The same rules as for people (length, not too common): a
            # service password guessed through /api/token/ opens the orders
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error

        created = user.pk is None
        with transaction.atomic():
            user.is_staff = False
            user.is_superuser = False
            user.is_active = True
            user.set_password(password)
            user.save()
            user.groups.add(group)

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action}: {username} (group {SERVICES_GROUP})"))

    def ask_password(self):
        if not self.stdin_is_terminal():
            raise CommandError("Set the password variable: there is no terminal to ask in.")
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Password again: "):
            raise CommandError("The passwords differ.")
        if not password:
            raise CommandError("An empty password.")
        return password

    @staticmethod
    def stdin_is_terminal():
        # A function of its own: the tests replace it (pytest has no terminal)
        return os.isatty(0)
