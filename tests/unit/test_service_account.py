"""The rights of the Analytics service and the command create_service_account."""

import pytest
from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.utils import translation

from users.management.commands import create_service_account
from users.models import User

from ..factories import UserFactory

pytestmark = pytest.mark.django_db

PASSWORD = "Long-service-pass-42"


# Generated with AI
@pytest.mark.parametrize(
    "groups, export, view",
    [
        (["Services"], True, False),
        (["Managers"], False, True),
        (["Editors"], False, False),
        (["Customers"], False, False),
    ],
)
def test_the_groups_get_the_rights_of_the_migration(groups, export, view):
    user = UserFactory(groups=groups)

    assert user.has_perm("orders.export_orders_for_analytics") is export
    assert user.has_perm("orders.view_sales_analytics") is view


# Generated with AI
def test_the_command_creates_a_service_account(monkeypatch, capsys):
    monkeypatch.setenv("ANALYTICS_SERVICE_PASSWORD", PASSWORD)

    call_command("create_service_account", "analytics-service")

    user = User.objects.get(username="analytics-service")
    assert user.check_password(PASSWORD)
    assert list(user.groups.values_list("name", flat=True)) == ["Services"]
    assert (user.is_staff, user.is_superuser, user.is_active) == (False, False, True)
    # Required and unique, never deliverable (the reserved domain .invalid)
    assert user.email == "analytics-service@services.invalid"
    assert "Created: analytics-service" in capsys.readouterr().out


# Generated with AI
def test_repeating_it_updates_the_password_and_takes_away_extra_rights(monkeypatch, capsys):
    UserFactory(username="analytics-service", is_staff=True, is_superuser=True, is_active=False)
    monkeypatch.setenv("SERVICE_PASSWORD", PASSWORD)

    call_command("create_service_account", "analytics-service", password_env="SERVICE_PASSWORD")

    user = User.objects.get(username="analytics-service")
    assert user.check_password(PASSWORD)
    assert (user.is_staff, user.is_superuser, user.is_active) == (False, False, True)
    assert user.groups.filter(name="Services").exists()
    assert "Updated: analytics-service" in capsys.readouterr().out


# Generated with AI
def test_a_weak_password_is_refused(monkeypatch):
    monkeypatch.setenv("ANALYTICS_SERVICE_PASSWORD", "12345")

    with translation.override("en"), pytest.raises(CommandError, match="too short"):
        call_command("create_service_account", "analytics-service")
    assert not User.objects.filter(username="analytics-service").exists()


# Generated with AI
def test_without_the_group_it_asks_for_migrate(monkeypatch):
    monkeypatch.setenv("ANALYTICS_SERVICE_PASSWORD", PASSWORD)
    Group.objects.filter(name="Services").delete()

    with pytest.raises(CommandError, match="migrate"):
        call_command("create_service_account", "analytics-service")


# Generated with AI
def test_without_a_variable_the_password_is_asked(monkeypatch):
    monkeypatch.delenv("ANALYTICS_SERVICE_PASSWORD", raising=False)
    monkeypatch.setattr(
        create_service_account.Command, "stdin_is_terminal", staticmethod(lambda: True)
    )
    monkeypatch.setattr(create_service_account.getpass, "getpass", lambda prompt: PASSWORD)

    call_command("create_service_account", "analytics-service")

    assert User.objects.get(username="analytics-service").check_password(PASSWORD)


# Generated with AI
def test_two_different_typed_passwords_are_refused(monkeypatch):
    monkeypatch.delenv("ANALYTICS_SERVICE_PASSWORD", raising=False)
    monkeypatch.setattr(
        create_service_account.Command, "stdin_is_terminal", staticmethod(lambda: True)
    )
    answers = iter([PASSWORD, "something else"])
    monkeypatch.setattr(create_service_account.getpass, "getpass", lambda prompt: next(answers))

    with pytest.raises(CommandError, match="differ"):
        call_command("create_service_account", "analytics-service")


# Generated with AI
def test_an_empty_typed_password_is_refused(monkeypatch):
    monkeypatch.delenv("ANALYTICS_SERVICE_PASSWORD", raising=False)
    monkeypatch.setattr(
        create_service_account.Command, "stdin_is_terminal", staticmethod(lambda: True)
    )
    monkeypatch.setattr(create_service_account.getpass, "getpass", lambda prompt: "")

    with pytest.raises(CommandError, match="empty"):
        call_command("create_service_account", "analytics-service")


# Generated with AI
def test_without_a_variable_and_a_terminal_it_stops(monkeypatch):
    monkeypatch.delenv("ANALYTICS_SERVICE_PASSWORD", raising=False)
    monkeypatch.setattr(
        create_service_account.Command, "stdin_is_terminal", staticmethod(lambda: False)
    )

    with pytest.raises(CommandError, match="no terminal"):
        call_command("create_service_account", "analytics-service")
