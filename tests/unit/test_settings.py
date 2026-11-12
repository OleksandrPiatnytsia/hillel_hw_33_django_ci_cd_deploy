"""Settings: the helpers of config/env.py and the production settings.

The tests themselves run with config.settings.test. The production
settings are loaded in a separate Python process (subprocess): importing
them here would mix them into the test settings, and their start checks
(no DJANGO_ALLOWED_HOSTS -> error) are exactly what is tested.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.env import database_settings, env_bool, env_list, redis_url

BASE_DIR = Path(__file__).resolve().parents[2]  # the folder with manage.py

# ---------------------------------------------------------------------------
# config/env.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("True", True), ("1", True), (" yes ", True), ("on", True), ("False", False), ("", False)],
)
def test_env_bool(monkeypatch, value, expected):
    monkeypatch.setenv("SOME_FLAG", value)

    assert env_bool("SOME_FLAG", default=not expected) is expected


def test_env_bool_not_set_gives_the_default(monkeypatch):
    monkeypatch.delenv("SOME_FLAG", raising=False)

    assert env_bool("SOME_FLAG", True) is True
    assert env_bool("SOME_FLAG", False) is False


def test_env_list(monkeypatch):
    monkeypatch.setenv("SOME_HOSTS", " a.com, b.com,,")
    monkeypatch.delenv("NO_HOSTS", raising=False)

    assert env_list("SOME_HOSTS") == ["a.com", "b.com"]
    assert env_list("NO_HOSTS") == []


def test_database_from_database_url(monkeypatch):
    # The password "p@ss/word" comes %-encoded in a URL
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://shop:p%40ss%2Fword@db.example.com:6543/books?sslmode=require"
    )

    assert database_settings() == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "books",
        "USER": "shop",
        "PASSWORD": "p@ss/word",
        "HOST": "db.example.com",
        "PORT": "6543",
        "OPTIONS": {"sslmode": "require"},
    }


def test_database_url_without_port_uses_5432(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://shop:secret@db.example.com/books")

    assert database_settings()["PORT"] == "5432"


def test_database_from_postgres_variables(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for name, value in {
        "POSTGRES_DB": "books",
        "POSTGRES_USER": "shop",
        "POSTGRES_PASSWORD": "secret",
        "POSTGRES_HOST": "db",
        "POSTGRES_PORT": "5433",
    }.items():
        monkeypatch.setenv(name, value)

    database = database_settings()

    assert (database["NAME"], database["USER"], database["PASSWORD"]) == ("books", "shop", "secret")
    assert (database["HOST"], database["PORT"]) == ("db", "5433")
    assert database["OPTIONS"] == {}


def test_database_url_must_be_postgresql(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://shop:secret@db.example.com/books")

    with pytest.raises(ImproperlyConfigured, match="postgresql://"):
        database_settings()


@pytest.mark.parametrize(
    ("url", "database", "expected"),
    [
        # Railway: a password, no database number
        (
            "redis://default:secret@redis.internal:6379",
            1,
            "redis://default:secret@redis.internal:6379/1",
        ),
        # An old .env with a number: replaced
        ("redis://localhost:6379/0", 1, "redis://localhost:6379/1"),
        ("redis://localhost:6379/", 0, "redis://localhost:6379/0"),
    ],
)
def test_redis_url(url, database, expected):
    assert redis_url(url, database) == expected


# ---------------------------------------------------------------------------
# config/settings/production.py (in a separate process)
# ---------------------------------------------------------------------------

# Long and random-looking: check --deploy warns about short or
# "django-insecure-" keys (security.W009). Not used anywhere else.
PRODUCTION_KEY = "test-only-" + "k8Qz3vN7pW2xR9mT4bY6hL1sD5fG0jC" * 2


def run_with_production_settings(*args, **env):
    """Runs a command of manage.py with the production settings.

    The environment of this test process (POSTGRES_* or DATABASE_URL from
    .env / CI) + the given variables. SENTRY_DSN is emptied: a real DSN from
    .env must not get the errors these tests cause on purpose.
    """
    # Without DJANGO_HTTPS of this process: the default (True) unless a test
    # sets it
    inherited = {name: value for name, value in os.environ.items() if name != "DJANGO_HTTPS"}
    environment = {
        **inherited,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": PRODUCTION_KEY,
        "DJANGO_ALLOWED_HOSTS": "bookstore.example.com",
        "SENTRY_DSN": "",
        **env,
    }
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=BASE_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


SETTINGS_TO_JSON = (
    "import json; from django.conf import settings as s; print(json.dumps({"
    "'DEBUG': s.DEBUG, 'SECURE_SSL_REDIRECT': s.SECURE_SSL_REDIRECT, "
    "'SESSION_COOKIE_SECURE': s.SESSION_COOKIE_SECURE, "
    "'SECURE_HSTS_SECONDS': s.SECURE_HSTS_SECONDS, "
    "'SECURE_REDIRECT_EXEMPT': s.SECURE_REDIRECT_EXEMPT, "
    "'MIDDLEWARE': s.MIDDLEWARE, 'SERVE_MEDIA': s.SERVE_MEDIA, "
    "'STATICFILES': s.STORAGES['staticfiles']['BACKEND']}))"
)


def production_settings(**env):
    # --no-imports: no "21 objects imported automatically" line before the JSON
    result = run_with_production_settings("shell", "--no-imports", "-c", SETTINGS_TO_JSON, **env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_production_settings_pass_the_deploy_check():
    """manage.py check --deploy: Django's own list of production problems
    (DEBUG, SECRET_KEY, HTTPS, secure cookies, HSTS, ...). Any warning fails."""
    result = run_with_production_settings("check", "--deploy", "--fail-level", "WARNING")

    assert result.returncode == 0, result.stderr
    assert "no issues" in result.stdout


def test_production_settings_have_https_and_no_debug():
    values = production_settings(DJANGO_DEBUG="True")  # ignored by production

    assert values["DEBUG"] is False
    assert values["SECURE_SSL_REDIRECT"] is True
    assert values["SESSION_COOKIE_SECURE"] is True
    assert values["SECURE_HSTS_SECONDS"] == 3600
    assert values["STATICFILES"] == "whitenoise.storage.CompressedManifestStaticFilesStorage"
    assert values["SERVE_MEDIA"] is False  # only with DJANGO_SERVE_MEDIA=True


def test_production_serves_static_files_with_whitenoise():
    """Railway has no nginx: WhiteNoise right after SecurityMiddleware
    (the HTTPS redirect first, then a static file skips the rest)."""
    middleware = production_settings()["MIDDLEWARE"]

    security = middleware.index("django.middleware.security.SecurityMiddleware")
    assert middleware[security + 1] == "whitenoise.middleware.WhiteNoiseMiddleware"


def test_production_serves_media_with_the_flag():
    assert production_settings(DJANGO_SERVE_MEDIA="True")["SERVE_MEDIA"] is True


def test_production_settings_without_https_for_local_docker():
    values = production_settings(DJANGO_HTTPS="False")

    assert values["DEBUG"] is False
    assert values["SECURE_SSL_REDIRECT"] is False
    assert values["SESSION_COOKIE_SECURE"] is False
    assert values["SECURE_HSTS_SECONDS"] == 0


def test_production_settings_refuse_to_start_without_allowed_hosts():
    result = run_with_production_settings("check", DJANGO_ALLOWED_HOSTS="")

    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS is empty" in result.stderr


@pytest.mark.django_db
def test_https_redirect_skips_the_health_check(client, settings):
    """Railway calls /health/ over plain http, without the proxy: a 301 to
    https:// would be a failed health check. The other pages are redirected."""
    settings.SECURE_SSL_REDIRECT = True
    settings.SECURE_REDIRECT_EXEMPT = production_settings()["SECURE_REDIRECT_EXEMPT"]

    assert client.get("/health/").status_code != 301
    catalog = client.get("/")
    assert catalog.status_code == 301
    assert catalog.url.startswith("https://")
