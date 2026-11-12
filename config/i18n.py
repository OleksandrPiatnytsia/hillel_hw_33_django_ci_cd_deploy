"""Language of the site: the cookie, and the user's saved language.

The language of a request comes from the "django_language" cookie
(LocaleMiddleware, see "Internationalization" in config/settings/base.py). The cookie
is set in two places:
- the switcher in the navbar -> config.views.set_language;
- the login -> users.views.UserLoginView: the language saved in the
  profile (User.language), so a user gets their language on a new device.
"""

from django.conf import settings


def is_supported_language(language):
    """Only the codes from settings.LANGUAGES ("uk", "en")."""
    return language in dict(settings.LANGUAGES)


def set_language_cookie(response, language):
    """Put the language cookie on the response, with the same parameters
    Django's set_language view uses (name, age, path, secure, ...)."""
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        language,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        path=settings.LANGUAGE_COOKIE_PATH,
        domain=settings.LANGUAGE_COOKIE_DOMAIN,
        secure=settings.LANGUAGE_COOKIE_SECURE,
        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
    )
    return response
