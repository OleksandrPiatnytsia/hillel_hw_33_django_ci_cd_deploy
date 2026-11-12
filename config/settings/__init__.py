# Settings package: base.py (shared) + one module per environment,
# chosen by DJANGO_SETTINGS_MODULE (see the docstring of base.py):
#   config.settings.development   runserver (manage.py default)
#   config.settings.production    Docker, Railway (Dockerfile)
#   config.settings.test          pytest (pytest.ini)
# Nothing is imported here: "config.settings" alone is not a settings module.
