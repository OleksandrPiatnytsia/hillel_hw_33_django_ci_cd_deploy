"""Settings shared by every environment.

The settings are a package; DJANGO_SETTINGS_MODULE picks one module, and
each of them starts with "from .base import *" and changes only its part:

    config.settings.development  runserver on your machine: DEBUG, Debug
                                 Toolbar, DEBUG logs (manage.py default)
    config.settings.production   Docker, Railway: DEBUG off, HTTPS and
                                 security headers, hashed static files
                                 (default of asgi.py / wsgi.py / celery.py
                                 and set in the Dockerfile)
    config.settings.test         pytest (pytest.ini): fast hasher, cache in
                                 memory, eager Celery

This file is safe on its own: DEBUG is off, and everything secret or
different per machine comes from environment variables (.env locally, the
variables of the service on a hosting).
https://docs.djangoproject.com/en/6.1/topics/settings/
https://docs.djangoproject.com/en/6.1/ref/settings/
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
from corsheaders.defaults import default_headers
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv

from config.env import database_settings, env_list, redis_url

# The project folder (the one with manage.py): config/settings/base.py is
# three levels below it. Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load variables from .env file in project root
load_dotenv(BASE_DIR / ".env")


# Deployment checklist: https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/
# (python manage.py check --deploy with the production settings)

# Signs sessions, CSRF tokens, password reset links and the JWT tokens:
# required, no default. A default in the code would be the same on every
# server, and anyone who reads the repository could forge a login.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

# Off here; only development.py turns it on. DEBUG=True shows the code,
# the settings and the SQL of any error page to every visitor.
DEBUG = False

# Host names the site answers to (the Host header), comma separated:
# DJANGO_ALLOWED_HOSTS=bookstore.up.railway.app. Any other host -> 400,
# so a fake Host can't get into the links Django builds (password emails).
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # REST API (settings in the "REST API" section below)
    "rest_framework",
    # Not for models (we don't use the token blacklist): its translations
    # of the error messages ("Token is invalid or expired") come with the app
    "rest_framework_simplejwt",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    # Local apps
    "users",
    "books",
    # Warehouses and the stock of books (was the column Book.stock)
    "inventory",
    "cart",
    "orders",
    "payments",
    # The whole REST API layer: serializers, ViewSets, permissions, URLs
    "api",
]

# Custom user model (users.User instead of auth.User). Must be set before
# the very first `migrate`: other tables (admin log, groups, permissions)
# get a foreign key to this model's table.
AUTH_USER_MODEL = "users.User"

# Where login_required / LoginRequiredMixin send anonymous users
# (URL names are fine here: Django resolves them with reverse())
LOGIN_URL = "users:login"
# After login, if there is no ?next=...
LOGIN_REDIRECT_URL = "books:list"
# After logout
LOGOUT_REDIRECT_URL = "books:list"

MIDDLEWARE = [
    # Our middleware, first: its timer covers every middleware below + the view
    "config.middleware.RequestTimingMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # No static files middleware: in Docker nginx serves /static/ and
    # /media/ itself (nginx/default.conf), the request never reaches Django;
    # runserver (DEBUG=True) serves static files by itself.
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Chooses the language of every request (see "Internationalization"
    # below) and activates it for the view and the templates. After
    # SessionMiddleware, before CommonMiddleware (Django docs).
    "django.middleware.locale.LocaleMiddleware",
    # CORS headers (Access-Control-Allow-Origin, ...) for /api/ only, see
    # CORS_URLS_REGEX. Before CommonMiddleware (django-cors-headers docs):
    # a redirect made by CommonMiddleware (adding the "/") gets them too.
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Are we running the tests? `manage.py test`, or pytest (pytest-django
# imports the settings after pytest itself, so "pytest" is already loaded).
TESTING = "test" in sys.argv or "pytest" in sys.modules

# Django Debug Toolbar: turned on in development.py only (config/urls.py
# adds its URLs when this is True)
ENABLE_DEBUG_TOOLBAR = False

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Project-wide templates (base.html, navbar, pagination, ...)
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # "cart" in every template: navbar counter, cart page
                "cart.context_processors.cart",
            ],
        },
    },
]

# runserver and `manage.py` use WSGI; Docker runs the ASGI application
# (config/asgi.py) with gunicorn + uvicorn workers: see the Dockerfile
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

#
# PostgreSQL only. The connection comes from environment variables, one of:
#   - DATABASE_URL=postgresql://user:password@host:5432/name: Railway gives
#     it to the services linked to its PostgreSQL; GitHub Actions sets it too;
#   - POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD (required) +
#     POSTGRES_HOST / POSTGRES_PORT (localhost:5432 by default): .env and
#     docker-compose.yml. The postgres Docker image reads the same names and
#     creates this database and user on its first start, so one .env serves
#     both. POSTGRES_HOST is "localhost" for runserver and the tests (the
#     port published by the db container) and "db" (the service name)
#     inside docker compose.
# config/env.py: database_settings() reads them.
# The underscore: "from .base import *" doesn't copy this helper variable.
_database = database_settings()

DATABASES = {
    "default": {
        **_database,
        # A POOL of open connections (psycopg_pool) instead of persistent
        # connections (CONN_MAX_AGE). Under ASGI (gunicorn + uvicorn) the
        # async views run the ORM in worker threads, and a persistent
        # connection is kept per thread: threads come and go, their
        # connections stay open (Django docs: "disable persistent
        # connections" under ASGI). A pool shares a few connections between
        # all threads of a process: a request takes one, gives it back at
        # the end. CONN_MAX_AGE must stay 0 with a pool (Django checks it).
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            # ?sslmode=... of DATABASE_URL, if any
            **_database["OPTIONS"],
            "pool": {
                "min_size": 2,  # opened at start, always ready
                "max_size": 10,  # at most, per gunicorn worker process
                "timeout": 10,  # seconds to wait for a free connection
            },
        },
    }
}


# Cache: Redis
# https://docs.djangoproject.com/en/6.1/topics/cache/#redis
#
# Django's built-in Redis backend (needs the `redis` package).
# REDIS_URL: redis://[user:password@]host:port, the address of the Redis
# server: "localhost" for runserver, redis://redis:6379 in docker compose
# (the service name), Railway gives its own with a password.
# One server, two databases (config/env.py redis_url): 0 = the cache and
# sessions, 1 = the Celery queue (see below). A number at the end of
# REDIS_URL (.../0) is replaced, so old .env files keep working.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": redis_url(REDIS_URL, 0),
    }
}

# How long cached data lives. Changes delete it at once (signals in
# books/signals.py and api/signals.py); the timeout is a safety net for a
# change that skips the signals (QuerySet.update(), SQL by hand).
# Book page object + HTML fragments of books (books/cache.py)
BOOK_CACHE_TIMEOUT = int(os.getenv("BOOK_CACHE_TIMEOUT", 60 * 60))  # 1 hour
# Whole responses of /api/authors/ and /api/categories/ (api/cache.py)
API_CACHE_TIMEOUT = int(os.getenv("API_CACHE_TIMEOUT", 10 * 60))  # 10 minutes

# Sessions: read from the Redis cache, written to both the cache and the
# database (django_session table). Fast reads, and the logins survive a
# Redis restart: on a cache miss Django reads the session from PostgreSQL.
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"


# Celery: background tasks (config/celery.py, <app>/tasks.py)
# https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html
#
# Every CELERY_* setting here is a Celery setting without the prefix
# (config_from_object(..., namespace="CELERY")): CELERY_BROKER_URL -> broker_url.
#
# The broker is the queue of tasks: the site puts a message "send the email
# of order 5" there, a worker process (service "celery") takes it and runs
# the task. Redis database 1: the cache and sessions are in database 0,
# a FLUSHDB of one never touches the other.
# CELERY_BROKER_URL: only to put the queue on another server; by default
# it's the REDIS_URL server, database 1.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or redis_url(REDIS_URL, 1)
# No result backend: nobody waits for a return value (emails, reports,
# cleanup); the outcome of every task is in the log
CELERY_TASK_IGNORE_RESULT = True
# CELERY_TIMEZONE: next to TIME_ZONE below
# Celery 5.x warns at start without it: keep trying to connect to Redis
# while the worker starts (Redis may start a second later than the worker)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# A message is removed from the queue only AFTER the task has finished: a
# worker killed in the middle (docker compose restart) doesn't lose it,
# another worker runs it again. Our tasks are safe to run twice.
CELERY_TASK_ACKS_LATE = True
# One task at a time per worker process: long tasks (the report) don't
# hold a pile of reserved messages that other processes could run
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# A task that runs longer is stopped (a hung SMTP server, a huge report):
# soft -> SoftTimeLimitExceeded inside the task, hard -> the process is killed
CELERY_TASK_SOFT_TIME_LIMIT = 5 * 60
CELERY_TASK_TIME_LIMIT = 6 * 60
# Events for Flower (service "flower"): the worker reports every step of a
# task (received, started, succeeded / failed / retried) to the broker,
# Flower reads them and shows the tasks live. Without these Flower sees the
# workers but an empty task list.
#   WORKER_SEND_TASK_EVENTS: the worker's events (= celery worker -E)
#   TASK_SEND_SENT_EVENT:    + "sent" when web / beat put a task into the
#                            queue, so a task waiting for a free worker
#                            is visible too (state PENDING -> RECEIVED ...)
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True
# Where the browser opens Flower: the link in the profile ("Tools").
# docker-compose.yml publishes it on this Mac only.
FLOWER_URL = os.getenv("FLOWER_URL", "http://localhost:5555")

# Celery Beat: the schedule of periodic tasks (service "celery-beat").
# Beat only PUTS the tasks into the queue at these moments; the worker runs
# them. Kept here, in code (not django-celery-beat in the admin): the
# schedule is reviewed in git like the rest of the code.
# crontab(minute=0) = every hour at :00; crontab(hour=3, minute=0) = 03:00.
CELERY_BEAT_SCHEDULE = {
    # Orders unpaid for more than ORDER_UNPAID_MAX_AGE_HOURS: books back to stock
    "cancel-unpaid-orders": {
        "task": "orders.tasks.cancel_unpaid_orders",
        "schedule": crontab(minute=0),
    },
    # Expired sessions out of the django_session table
    "clear-expired-sessions": {
        "task": "users.tasks.clear_expired_sessions",
        "schedule": crontab(hour=3, minute=0),
    },
    # Yesterday's sales, top books, low stock -> email to "Managers"
    "daily-sales-report": {
        "task": "orders.tasks.send_daily_report",
        "schedule": crontab(hour=6, minute=0),
    },
}
# Age of an unpaid order for the hourly cancel_unpaid_orders task
ORDER_UNPAID_MAX_AGE_HOURS = int(os.getenv("ORDER_UNPAID_MAX_AGE_HOURS", 24))


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

#
# Two languages: Ukrainian (default) and English. The texts in the code and
# the templates stay in English (msgid); the Ukrainian translations are in
# locale/uk/LC_MESSAGES/django.po (compiled to django.mo).
#
# How the language of a request is chosen (LocaleMiddleware), first match wins:
#   1. the "django_language" cookie: set by the switcher in the navbar
#      (config.views.set_language) and at login (the user's saved language);
#   2. the Accept-Language header of the browser (a first visit);
#   3. LANGUAGE_CODE.
# No language prefix in the URLs (/uk/..., i18n_patterns): Stripe's return
# URLs, the webhook and the links in emails stay the same for everybody.

LANGUAGE_CODE = "uk"

# Only these two can be activated. gettext_lazy: the names are translated
# when shown (the switcher shows the native names, see navbar.html).
LANGUAGES = [
    ("uk", _("Ukrainian")),
    ("en", _("English")),
]

# Our translations (makemessages / compilemessages); Django's own (admin,
# form errors, ...) come with Django.
LOCALE_PATHS = [BASE_DIR / "locale"]

# The language cookie lives a year. Default None = until the browser is
# closed: the site would switch back to Ukrainian every time.
LANGUAGE_COOKIE_AGE = 365 * 24 * 60 * 60

TIME_ZONE = "UTC"
# Celery uses the same clock: the crontab hours of CELERY_BEAT_SCHEDULE
# and "yesterday" of the daily report are UTC, like every date of the site
CELERY_TIMEZONE = TIME_ZONE

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = "static/"

# Project-wide static files (css, images) that don't belong to a single app
STATICFILES_DIRS = [BASE_DIR / "static"]

# Target directory for `collectstatic` (used in production, not in git).
# In Docker it is a volume (static_data): web fills it on start
# (docker-entrypoint.sh), nginx serves it at /static/.
STATIC_ROOT = BASE_DIR / "staticfiles"

# https://docs.djangoproject.com/en/6.1/ref/settings/#storages
# "default" is Django's usual storage for uploaded files (covers in MEDIA_ROOT).
# "staticfiles": the plain names (css/styles.css), no collectstatic needed:
# runserver and the tests. production.py replaces it with the hashed names.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


# Media files (uploaded by users: book covers)
# https://docs.djangoproject.com/en/6.1/topics/files/

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

#
# Django 6.1: MAILERS replaces the old EMAIL_BACKEND / EMAIL_HOST / ...
# settings (deprecated, removed in Django 7.0). The "default" mailer is used
# by send_mail() and EmailMessage.send(). Tests don't send real emails: the
# test runner replaces every mailer with the locmem backend (mail.outbox).
#
# Gmail SMTP: login = the Gmail address, password = an App Password
# (16 letters, Google account -> Security -> 2-Step Verification ->
# App passwords), NOT the account password. Limit ~500 emails per day.
# Without these two variables emails are printed to the console (the
# terminal of runserver / `docker compose logs web`) — handy without Gmail.
EMAIL_USER = os.getenv("EMAIL_HOST_USER", "")
# Google shows the password in groups "abcd efgh ijkl mnop"; spaces out
EMAIL_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "").replace(" ", "")

if EMAIL_USER and EMAIL_PASSWORD:
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {
                "host": "smtp.gmail.com",
                # 587 + use_tls: connect in plain text, then STARTTLS
                # upgrades the connection to TLS before the login
                "port": 587,
                "use_tls": True,
                "username": EMAIL_USER,
                "password": EMAIL_PASSWORD,
                # Seconds; without it a stuck connection would hang the
                # request that sends the email forever
                "timeout": 10,
            },
        },
    }
else:
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.console.EmailBackend",
        },
    }

# "From" of the emails. Gmail sends only from the account it logs in with
# (another address is replaced by it), so it's the same address with a name.
DEFAULT_FROM_EMAIL = f"Bookstore <{EMAIL_USER or 'noreply@localhost'}>"

# Stripe (payments/providers/stripe_checkout.py). Test mode keys start with
# sk_test_: no real money, test cards like 4242 4242 4242 4242.
# Empty -> the "Pay" button answers "Online payment is not configured".
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
# Signing secret of the webhook (whsec_...): proves that a request to
# /payments/webhook/stripe/ comes from Stripe. Stripe CLI prints it:
#   docker compose run --rm stripe-cli listen --print-secret
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Address of the site for links in emails. An email is sent without a
# request (after COMMIT, from the Stripe webhook), so request.build_absolute_uri()
# is not available there.
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").rstrip("/")


# REST API (app api/, URLs under /api/)
# https://www.django-rest-framework.org/api-guide/settings/

REST_FRAMEWORK = {
    # Who is the user of an API request; the first class that recognises
    # the request wins:
    #   - JWT: header "Authorization: Bearer <access token>" (other
    #     services, mobile apps, a frontend on another domain);
    #   - session: the cookie of the site login. For the browsable API and
    #     Swagger in the same browser. It checks the CSRF token for POST /
    #     PATCH / DELETE, so another site can't use the visitor's cookie.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Closed by default: a new endpoint without its own permission_classes
    # requires a login instead of being open to everybody by mistake.
    # The catalog (read for everybody) and the others set their own.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Every list: 20 objects per page, ?page=2 for the next ones.
    # The answer: {"count": 135, "next": "...?page=2", "previous": null,
    # "results": [...]}
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # ?category=3&author=5 (FilterSet classes), ?search=... and
    # ?ordering=-price for the ViewSets that declare the fields
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        # OrderingFilter of DRF + "pk" as the last column: a stable order
        # for the pages (api/filters.py)
        "api.filters.StableOrderingFilter",
    ],
    # Request limits. Counters live in the cache (Redis; in tests the
    # in-memory cache, cleared before every test). Over the limit:
    # 429 Too Many Requests + header Retry-After (seconds to wait).
    #   - anonymous: counted per IP address;
    #   - user: per user id, whichever IP address the requests come from.
    # The IP of an anonymous client = REMOTE_ADDR only. The default (None)
    # takes X-Forwarded-For when the request has it, and any client can
    # send that header with a new made-up address every time, so the "anon"
    # limit would never be reached. Behind nginx REMOTE_ADDR is already the
    # real client address (gunicorn --forwarded-allow-ips, see Dockerfile).
    "NUM_PROXIES": 0,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        # Getting a token = checking a password: a low limit against
        # password guessing (api.views.ThrottledTokenObtainPairView)
        "token": "10/minute",
    },
    # The OpenAPI schema for /api/docs/ is built by drf-spectacular
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# JWT tokens (djangorestframework-simplejwt)
# https://django-rest-framework-simplejwt.readthedocs.io/en/latest/settings.html
#
#   POST /api/token/          {"username", "password"} -> {"access", "refresh"}
#   POST /api/token/refresh/  {"refresh"}              -> {"access"}
#   POST /api/token/verify/   {"token"}                -> 200 or 401
#
# The access token goes with every request; it is short: a stolen one works
# only for 15 minutes. The refresh token only gets new access tokens.
# Signed with SECRET_KEY (algorithm HS256): changing the key makes every
# issued token invalid.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    # The header is "Authorization: Bearer <token>"
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# API documentation (drf-spectacular): /api/schema/ (OpenAPI, YAML),
# /api/docs/ (Swagger UI), /api/redoc/ (ReDoc)
# https://drf-spectacular.readthedocs.io/en/latest/settings.html
SPECTACULAR_SETTINGS = {
    "TITLE": "Bookstore API",
    "DESCRIPTION": (
        "REST API of the bookstore: the catalog (books, authors, "
        "categories) and orders. Authentication: JWT "
        '(POST /api/token/, then the header "Authorization: Bearer '
        '<access>") or the session of the site login.'
    ),
    "VERSION": "1.0.0",
    # The schema itself is not shown as an endpoint in Swagger
    "SERVE_INCLUDE_SCHEMA": False,
    # Separate request and response models (BookRequest / Book): the
    # read-only fields (id, created_at) are not in the request form
    "COMPONENT_SPLIT_REQUEST": True,
    # Run on the finished schema: the default hook (enums as named
    # components: OrderStatusEnum, ...) + ours (no developer docstrings of
    # the serializers in the "Schemas" section, api/docs.py)
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "api.docs.remove_component_descriptions",
    ],
    "SWAGGER_UI_SETTINGS": {
        # Swagger remembers the token after "Authorize" until the page closes
        "persistAuthorization": True,
    },
}

# CORS: may JavaScript from another domain call our API?
# https://github.com/adamchainz/django-cors-headers
#
# A browser lets a page from http://localhost:3000 read an answer from
# http://localhost:8000 only if the answer has
# "Access-Control-Allow-Origin: http://localhost:3000". Servers, curl and
# Postman don't care about CORS, only browsers do.
# The list comes from .env (comma separated), empty = nobody.
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
# Only the API: the pages of the site (forms, the cart, the payment) are
# never opened to other domains
CORS_URLS_REGEX = r"^/api/.*$"
# Headers a page from another domain may send: the standard ones
# (authorization, content-type, ...) + Idempotency-Key of POST /api/orders/.
# Without it the browser's preflight check fails and the POST is never sent.
CORS_ALLOW_HEADERS = (*default_headers, "idempotency-key")
# Answer headers its JavaScript may read (the others are hidden by the browser)
CORS_EXPOSE_HEADERS = ["Idempotent-Replayed"]


# Logging
# https://docs.djangoproject.com/en/6.1/topics/logging/
#
# Loggers are named after modules: logging.getLogger(__name__) in
# books/views.py gives "books.views", a child of the "books" logger below,
# so its records go to the handlers of "books".

LOGS_DIR = BASE_DIR / "logs"
# RotatingFileHandler doesn't create folders; logs/ is not in git
LOGS_DIR.mkdir(exist_ok=True)

# Our own code: INFO and above (development.py: DEBUG, everything)
APP_LOG_LEVEL = "INFO"
# Loggers of our apps, all with the same handlers and APP_LOG_LEVEL
# (orders.emails: "email sent" / "email failed" with the traceback)
APP_LOGGERS = ("books", "users", "orders", "payments", "api")

LOGGING = {
    "version": 1,
    # Keep Django's own loggers (django.server prints runserver requests)
    "disable_existing_loggers": False,
    "formatters": {
        # 2026-11-07 21:15:03,512 INFO users.signals Login: user=ann ip=127.0.0.1
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "filters": {
        "hide_client_error_traceback": {
            "()": "config.logging_filters.HideClientErrorTraceback",
        },
    },
    "handlers": {
        # The filter is on the handlers, not on the "django" logger: logger
        # filters don't apply to records coming up from child loggers
        # (django.request -> django). It touches only 4xx records anyway.
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["hide_client_error_traceback"],
        },
        "file": {
            # When app.log reaches 1 MB it is renamed to app.log.1
            # (app.log.1 -> app.log.2, ...), only the 5 newest are kept
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "app.log",
            "maxBytes": 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",  # book titles may be in Ukrainian
            "formatter": "verbose",
            "filters": ["hide_client_error_traceback"],
        },
    },
    "loggers": {
        # Django itself: only problems. django.request logs 404 ("Not Found"),
        # 403 ("Forbidden") as WARNING and 500 with a traceback as ERROR.
        # INFO would add noise like "Watching for file changes".
        "django": {
            "handlers": ["console", "file"],
            "level": "WARNING",
        },
        **{
            name: {
                "handlers": ["console", "file"],
                "level": APP_LOG_LEVEL,
                # Don't pass records up to the root logger: no duplicates
                "propagate": False,
            }
            for name in APP_LOGGERS
        },
        # config.middleware.RequestTimingMiddleware: one line per request
        "config": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        # Celery itself: "Task ... received / succeeded / retry", worker start
        "celery": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# RequestTimingMiddleware logs requests slower than this as WARNING
REQUEST_SLOW_MS = 500


# Sentry (sentry.io): errors of the site and of the Celery tasks.
# Empty SENTRY_DSN -> Sentry is off (runserver without a project, tests).
# At the end of the settings: init_sentry() starts the SDK in every process
# that loads them (web, celery, celery-beat). See config/sentry.py.
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
# "local" for runserver, "docker" in docker-compose.yml: a filter in Sentry
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "local")
# Part of the requests and tasks timed in Sentry -> Performance:
# 0.1 = every tenth; 0 = errors only. The free plan has a monthly limit.
# The project's Issues page, for the link in the profile ("Tools", superuser
# only): https://<org>.sentry.io/issues/?project=<id>. Empty -> no link.
SENTRY_ISSUES_URL = os.getenv("SENTRY_ISSUES_URL", "")
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

if not TESTING:
    # Imported only when needed: the tests never load the Sentry SDK
    from config.sentry import init_sentry

    init_sentry(
        SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    )
