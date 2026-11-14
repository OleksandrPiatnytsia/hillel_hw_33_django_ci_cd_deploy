"""The gunicorn worker of the site: uvicorn without the ASGI "lifespan" events.

At start uvicorn asks the app about "lifespan" (startup / shutdown hooks of
FastAPI or Starlette). Django doesn't support it and answers with
ValueError("Django can only handle ASGI/HTTP connections, not lifespan.").
uvicorn expects that and goes on, but Sentry catches the ValueError first
and reports it as an error: one event per worker on every start or deploy.
lifespan="off": uvicorn doesn't ask, so there is no ValueError at all.

Used in gunicorn.conf.py (worker_class). Docs:
https://www.uvicorn.org/settings/#implementation (--lifespan)
"""

from uvicorn_worker import UvicornWorker


class DjangoUvicornWorker(UvicornWorker):
    # The settings of uvicorn for every worker: the parent's (loop, http)
    # + lifespan off
    CONFIG_KWARGS = {**UvicornWorker.CONFIG_KWARGS, "lifespan": "off"}
