"""The Celery application of the project + enqueue_on_commit().

How a background task works:

    site (web)                     Redis db 1 (broker)          worker (celery)
    task.delay(5)  -- message -->  queue "celery"  -- message -->  runs task(5)

    celery-beat: puts the periodic tasks of CELERY_BEAT_SCHEDULE into the
    same queue at their time; it runs nothing itself.

Start (docker-compose.yml runs the same):
    celery -A config worker --loglevel=info
    celery -A config beat --loglevel=info

The tasks live in <app>/tasks.py (@shared_task) and are found by
autodiscover_tasks(): orders/tasks.py, payments/tasks.py, users/tasks.py.
"""

import logging
import os

from celery import Celery
from django.db import transaction

# Celery is started as its own program (celery -A config ...), not by
# manage.py: it must know the settings module itself. Production by default,
# like asgi.py / wsgi.py. Careful: config/__init__.py imports this file, so
# this line runs first in EVERY process that imports the config package
# (gunicorn too); manage.py sets its own default before that.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("config")
# Every Django setting that starts with CELERY_ is a Celery setting
# (CELERY_BROKER_URL -> broker_url)
app.config_from_object("django.conf:settings", namespace="CELERY")
# Import tasks.py of every app in INSTALLED_APPS
app.autodiscover_tasks()

logger = logging.getLogger(__name__)  # "config.celery"


def enqueue_on_commit(task, *args):
    """Put the task into the queue after COMMIT; run it here if Redis is down.

    After COMMIT, as before with the emails: a task sent inside the
    transaction could be taken by the worker before the COMMIT and not find
    the order yet (or find an order that is then rolled back).

    Broker down (Redis stopped, network): delay() raises an error after a
    few connection attempts. The order is already saved, so the customer
    must not get an error page: the task runs right here, in this process,
    like before Celery (slower answer, the email still goes out).
    task.apply(): synchronous, with the same retries, never raises.
    """

    def send():
        try:
            task.delay(*args)
        except Exception:
            logger.exception("Broker unavailable, running %s%s here", task.name, args)
            task.apply(args=args)

    transaction.on_commit(send)
