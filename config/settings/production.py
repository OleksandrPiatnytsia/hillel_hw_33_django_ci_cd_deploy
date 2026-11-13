"""Settings for servers: the Docker image (local docker compose, Railway).

The default of asgi.py, wsgi.py and celery.py, and set in the Dockerfile
(DJANGO_SETTINGS_MODULE=config.settings.production), so a server never runs
with DEBUG by mistake. Everything from base.py, plus:

- DEBUG off, no way to turn it on with a variable;
- a start without DJANGO_ALLOWED_HOSTS fails at once;
- HTTPS: redirect from http://, cookies only over HTTPS, HSTS
  (DJANGO_HTTPS=False turns these off for local docker compose, which has
  no certificate: http://localhost:8000);
- static files with a hash in the name (long browser cache), served by
  WhiteNoise where there is no nginx (Railway);
- covers (/media/) served by Django when DJANGO_SERVE_MEDIA=True (Railway).

Check: python manage.py check --deploy --settings=config.settings.production
(tests/unit/test_settings.py runs it).
"""

import os

from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_list

# F401 + F403: flake8 can't see which names come from "*"; settings modules
# are read by Django, nothing here uses them by name
from .base import *  # noqa: F401, F403
from .base import ALLOWED_HOSTS, MIDDLEWARE, STORAGES

DEBUG = False

# Railway: the host names it gives, without writing them by hand.
# - RAILWAY_PUBLIC_DOMAIN: the address of the service, e.g.
#   hillel-bookstore.up.railway.app (Railway sets it once the service has
#   a domain: Settings -> Networking -> Generate Domain);
# - healthcheck.railway.app: the Host of Railway's health check requests
#   (/health/). Not allowed = 400, the check fails, the deploy never goes
#   live. Added only on Railway (RAILWAY_ENVIRONMENT_NAME is set there).
# Docs: https://docs.railway.com/reference/variables
#       https://docs.railway.com/reference/healthchecks
RAILWAY_PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
if RAILWAY_PUBLIC_DOMAIN:
    ALLOWED_HOSTS.append(RAILWAY_PUBLIC_DOMAIN)
if os.getenv("RAILWAY_ENVIRONMENT_NAME"):
    ALLOWED_HOSTS.append("healthcheck.railway.app")

if not ALLOWED_HOSTS:
    # With DEBUG off and an empty list Django answers 400 to EVERY request,
    # the site looks down with no hint why. Better stop at start.
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS is empty: set the host names of the site, comma separated"
    )

# Pages sent by a form (POST) are accepted only from these origins, besides
# the site's own address. Not needed behind one proxy that passes the Host
# and the scheme (nginx, Railway): Django compares the Origin header with
# its own https://<host>. For a second domain in front of the site:
# DJANGO_CSRF_TRUSTED_ORIGINS=https://shop.example.com
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")


# ---------------------------------------------------------------------------
# HTTPS
# ---------------------------------------------------------------------------
# HTTPS ends at the proxy in front of the app (Railway's edge; nginx locally,
# without a certificate): the app itself gets plain http from it. The proxy
# says what the browser used in X-Forwarded-Proto, and with this setting
# request.is_secure() believes it. Safe only because every request comes
# through a proxy that sets this header itself (nginx/default.conf
# overwrites whatever the client sent; Railway does the same).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# True on a hosting with a certificate (the default); docker-compose.yml
# sets DJANGO_HTTPS=False: http://localhost:8000 has no HTTPS, and these
# settings would send the browser to https://localhost (nothing there) and
# never send the session cookie back over http (no login possible).
HTTPS = env_bool("DJANGO_HTTPS", True)

if HTTPS:
    # http://... -> 301 to https://... (SecurityMiddleware)
    SECURE_SSL_REDIRECT = True
    # Except the health check: Railway calls http://<container>:$PORT/health/
    # directly, without the proxy and without X-Forwarded-Proto. A redirect
    # would be a failed check, and the deploy would never go live.
    # The paths are regular expressions without the leading "/".
    SECURE_REDIRECT_EXEMPT = [r"^health/$"]

    # Cookies only over HTTPS: on an open Wi-Fi nobody can read the login
    # (session) from a plain http:// request
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    LANGUAGE_COOKIE_SECURE = True

    # HSTS (Strict-Transport-Security): the browser remembers to use only
    # HTTPS for this site, for SECURE_HSTS_SECONDS, even when someone types
    # http:// or a network tries to strip HTTPS. It can't be undone from the
    # server until the time passes, so it starts with 1 hour (Django's
    # advice); raise it to a year (31536000) when everything works.
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", 60 * 60))
    # Subdomains of the site too (bookstore.up.railway.app has none of its
    # own, so nothing can break)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # No preload: that is a request to put the domain into the list built
    # into browsers (hstspreload.org), possible only for a domain we own,
    # not for *.up.railway.app. check --deploy warns about it (W021).
    SECURE_HSTS_PRELOAD = False
    SILENCED_SYSTEM_CHECKS = ["security.W021"]

# Security headers that Django already sends by default (kept as they are,
# listed here so it's clear they are on):
#   X-Content-Type-Options: nosniff   SECURE_CONTENT_TYPE_NOSNIFF = True
#     the browser doesn't guess a type: an uploaded "cover" can't run as a script
#   X-Frame-Options: DENY             X_FRAME_OPTIONS = "DENY"
#     no other site can show ours in a frame (clickjacking)
#   Referrer-Policy: same-origin      SECURE_REFERRER_POLICY = "same-origin"
#     links to other sites don't get our addresses (order numbers in URLs)
#   Cross-Origin-Opener-Policy: same-origin
#                                     SECURE_CROSS_ORIGIN_OPENER_POLICY
#     a window opened by another site can't reach ours


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
# Railway runs only the image, there is no nginx in front of it, so Django
# itself must answer /static/... WhiteNoise does it fast: it reads the list
# of files in STATIC_ROOT once at start and sends them without the views,
# templates or the database. Locally nginx still answers /static/ before a
# request reaches Django, so there WhiteNoise just stays idle.
# Right after SecurityMiddleware (WhiteNoise docs): the HTTPS redirect and
# the security headers still apply, and a static file skips the sessions,
# auth and the rest of the chain.
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)

# CompressedManifestStaticFilesStorage (WhiteNoise) = Django's
# ManifestStaticFilesStorage + compression:
#   - collectstatic writes every file a second time with a hash of its
#     content in the name: css/styles.css -> css/styles.3f9a2c41b7e0.css,
#     and a list of them (staticfiles.json); {% static "css/styles.css" %}
#     gives the hashed name. A changed file = a new name, so the browsers
#     may keep the files for a year (WhiteNoise and nginx both send
#     Cache-Control "max-age=315360000, immutable" for hashed names): after
#     a deploy the pages link to the new names, nothing stale is used;
#   - + a .gz copy of every text file (CSS, JS, SVG): WhiteNoise sends it to
#     browsers that accept gzip, 3-5 times fewer bytes.
# Needs collectstatic before the start (docker-entrypoint.sh runs it).
STORAGES = {
    **STORAGES,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# ---------------------------------------------------------------------------
# Media files (book covers)
# ---------------------------------------------------------------------------
# Uploaded files can't go through WhiteNoise: it only knows the files that
# existed at start. On Railway the covers live on a Volume (/app/media) and
# Django serves them (config.views.serve_media). Fine for a small shop: a
# few covers per page, each cached by the browser for a week.
# Locally (docker compose) nginx serves /media/ from the media_data volume,
# so it stays False there.
SERVE_MEDIA = env_bool("DJANGO_SERVE_MEDIA", False)
