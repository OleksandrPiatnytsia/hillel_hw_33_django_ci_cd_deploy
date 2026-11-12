"""Reading settings from environment variables (config/settings/*.py).

Small helpers instead of a package (django-environ, dj-database-url): the
project needs only these few cases, and the code is easy to read and test.

Hosting services give the connections as ONE variable with a URL:
    DATABASE_URL=postgresql://user:password@host:5432/name
    REDIS_URL=redis://default:password@host:6379
Locally (.env, docker-compose.yml) the database still comes from the
separate POSTGRES_* variables, the ones the postgres Docker image reads too.
"""

import os
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

from django.core.exceptions import ImproperlyConfigured

TRUE_VALUES = ("true", "1", "yes", "on")


def env_bool(name, default):
    """DJANGO_DEBUG=True -> True. Not set -> default. Any other text -> False."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def env_list(name):
    """Comma separated: "a.com, b.com," -> ["a.com", "b.com"]. Not set or empty -> []."""
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def database_settings():
    """DATABASES["default"] without the pool part: from DATABASE_URL if it
    is set (Railway, CI), otherwise from POSTGRES_* (.env, docker compose).

    os.environ[...] (not getenv) for the required POSTGRES_* variables: a
    missing one stops Django at start with a clear KeyError instead of a
    vague connection error later.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ["POSTGRES_USER"],
            "PASSWORD": os.environ["POSTGRES_PASSWORD"],
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "OPTIONS": {},
        }

    parts = urlsplit(url)
    if parts.scheme not in ("postgres", "postgresql"):
        # The project uses PostgreSQL only (pool, migrations, tests)
        raise ImproperlyConfigured(
            f"DATABASE_URL must start with postgresql://, not {parts.scheme}://"
        )
    return {
        "ENGINE": "django.db.backends.postgresql",
        # unquote: special characters of a password come %-encoded in a URL
        # ("p@ss" -> "p%40ss"); the database needs the real ones
        "NAME": unquote(parts.path.lstrip("/")),
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname or "",
        "PORT": str(parts.port or 5432),
        # ?sslmode=require&connect_timeout=5 -> options of the connection
        "OPTIONS": dict(parse_qsl(parts.query)),
    }


def redis_url(url, database):
    """The same Redis server, another database number (the URL path).

    redis://host:6379      + 1 -> redis://host:6379/1
    redis://host:6379/0    + 1 -> redis://host:6379/1
    One REDIS_URL (Railway gives one, without a number) serves the cache and
    sessions (database 0) and the Celery queue (database 1).
    """
    return urlunsplit(urlsplit(url)._replace(path=f"/{database}"))
