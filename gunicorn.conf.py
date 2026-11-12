"""Settings of gunicorn, the server of the Docker image (Dockerfile CMD).

gunicorn reads ./gunicorn.conf.py by itself (the image runs in /app, next
to this file), so the command stays short:  gunicorn config.asgi:application
A Python file, not command-line flags: the values can come from environment
variables, which a hosting sets (Railway: PORT), and every one has a comment.

Docs: https://docs.gunicorn.org/en/stable/settings.html
"""

import os

# gunicorn as the process manager + uvicorn workers, i.e. an ASGI server
# (runserver is for development only: one process, not built for load or
# security). ASGI: the async views (health, order status, book search) run
# in an event loop; the sync views keep working as before (Django runs them
# in a thread). Every gunicorn worker process runs uvicorn (package
# uvicorn-worker): gunicorn restarts crashed workers, uvicorn speaks ASGI.
worker_class = "uvicorn_worker.UvicornWorker"

# Listen on all interfaces of the container (127.0.0.1 would be reachable
# only from inside it). The port: $PORT when the hosting sets it (Railway
# chooses the port and sends its traffic there), else 8000 (docker compose:
# nginx -> web:8000).
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Processes handling requests in parallel. Each one holds the whole app in
# memory (~100-150 MB), so a small hosting plan may need fewer:
# WEB_CONCURRENCY=2 (the usual name, Railway and Heroku docs use it too).
workers = int(os.getenv("WEB_CONCURRENCY", "3"))

# Trust X-Forwarded-For / X-Forwarded-Proto from any address. Requests come
# only from the proxy in front of the app (nginx locally: web has no
# published port; Railway's edge on a hosting), and the proxy sets these
# headers itself. uvicorn then puts the client's real address into
# REMOTE_ADDR and the scheme into request.is_secure(). The default
# (127.0.0.1) would ignore them: the proxy has another address.
forwarded_allow_ips = "*"

# No access log: RequestTimingMiddleware already logs one line per request,
# with the user and the duration; gunicorn's access log would repeat every
# request and add a line for every /health/ check. (The default is off,
# written here so nobody turns it on thinking it's missing.)
accesslog = None

# No control socket. Since gunicorn 25.1 it opens a unix socket for the
# `gunicornc` tool (worker status, reload) at $HOME/.gunicorn/gunicorn.ctl.
# Our "app" user has no home folder, so without this the log shows
# "Control server error: Permission denied: '/home/app'". We don't use
# gunicornc: a restart of the container is enough.
control_socket_disable = True
