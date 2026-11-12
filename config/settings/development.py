"""Settings for development on your machine: runserver, manage.py commands.

The default of manage.py (DJANGO_SETTINGS_MODULE not set). Everything from
base.py, plus:

- DEBUG on (DJANGO_DEBUG=False in .env turns it off, e.g. to see the 404 /
  500 pages as the visitors see them);
- Django Debug Toolbar, when it is installed (requirements-dev.txt);
- DEBUG logs of our own code.

Never on a server: the Docker image sets config.settings.production.
"""

from importlib.util import find_spec

from config.env import env_bool

# F401 + F403: flake8 can't see which names come from "*"; settings modules
# are read by Django, nothing here uses them by name
from .base import *  # noqa: F401, F403
from .base import APP_LOGGERS, INSTALLED_APPS, LOGGING, MIDDLEWARE, TESTING

DEBUG = env_bool("DJANGO_DEBUG", True)

# Django Debug Toolbar (development only, from requirements-dev.txt).
# Turned on only when ALL of these are true:
#   - DEBUG=True
#   - the package is installed: requirements.txt alone still works
#   - not the tests: the toolbar refuses to run in tests
ENABLE_DEBUG_TOOLBAR = DEBUG and find_spec("debug_toolbar") is not None and not TESTING

if ENABLE_DEBUG_TOOLBAR:
    INSTALLED_APPS += ["debug_toolbar"]
    # As early as possible, so it sees the work of every middleware below it
    # (sessions, auth, ...). After SecurityMiddleware, which only adds headers.
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
        "debug_toolbar.middleware.DebugToolbarMiddleware",
    )
    # The toolbar is shown only for requests from these addresses
    # (REMOTE_ADDR), in addition to DEBUG=True
    INTERNAL_IPS = ["127.0.0.1", "::1"]

# Our own code logs everything while developing (base.py: INFO)
if DEBUG:
    APP_LOG_LEVEL = "DEBUG"
    for name in APP_LOGGERS:
        LOGGING["loggers"][name]["level"] = APP_LOG_LEVEL
