"""Settings for the tests (pytest.ini: DJANGO_SETTINGS_MODULE = config.settings.test).

Everything from base.py (not development.py: no Debug Toolbar, DEBUG off,
like on a server), plus a few changes that make the tests fast, repeatable
and independent of the local .env:

- a fast password hasher: the default one (PBKDF2, ~1 million rounds) makes
  every create_user() / login take ~0.3 s;
- the cache in memory (LocMemCache) instead of Redis: tests don't touch
  the cache and sessions of the running site, and conftest.py clears it
  before every test;
- fixed fake Stripe keys: the Stripe client is replaced by a fake in tests
  (tests/fakes.py), the webhook secret signs the test webhook requests;
- no log file: test runs don't write to logs/app.log;
- no STATIC_ROOT: collectstatic is not needed for the tests (base.py
  keeps the plain static names, no manifest).

The database stays PostgreSQL from .env (the Docker db container on
localhost:5432) or DATABASE_URL (GitHub Actions): pytest-django creates a
separate database "test_<name>" next to the real one, the real data is
never touched.
Emails: pytest-django replaces every mailer with the locmem backend
(mail.outbox, the `mailoutbox` fixture), nothing is sent.
"""

# F401 + F403: flake8 can't see which names come from "*"; settings modules
# are read by Django, nothing here uses them by name
from .base import *  # noqa: F401, F403
from .base import DATABASES, LOGGING

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# No collected static files in tests ({% static %} still builds the URLs)
STATIC_ROOT = None

STRIPE_SECRET_KEY = "sk_test_fake"
STRIPE_WEBHOOK_SECRET = "whsec_test_fake"

# Links in emails; "testserver" is the host of Django's test client
SITE_URL = "http://testserver"
DEFAULT_FROM_EMAIL = "Bookstore <noreply@localhost>"

# CORS: fixed origins, the tests don't depend on CORS_ALLOWED_ORIGINS in .env
CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]

# Remove the "file" handler: dictConfig opens the file of every handler in
# the list, even an unused one. Records still go to the console handler,
# pytest captures them and shows them only for a failed test.
LOGGING["handlers"].pop("file")
for logger_config in LOGGING["loggers"].values():
    logger_config["handlers"] = [
        handler for handler in logger_config["handlers"] if handler != "file"
    ]

# No connection pool in tests: the pool keeps its connections to
# test_bookstore open until the process ends, and pytest-django can't drop
# the test database at the end ("is being accessed by other users").
# Without "pool" Django opens a connection per thread and closes it.
DATABASES["default"]["OPTIONS"].pop("pool", None)

# Celery in the tests: no broker, no worker. task.delay() runs the task
# right here, synchronously (with its retries, without the pauses), so the
# tests see the email in mail.outbox at once. EAGER_PROPAGATES=False: a
# task that fails after its retries doesn't raise in the test, as a failed
# background task never reaches the user.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False
