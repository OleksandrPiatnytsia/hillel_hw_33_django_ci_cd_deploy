#!/bin/sh
# Entrypoint of the containers built from the Dockerfile (web, celery,
# celery-beat): prepares Django, then starts the command.
#
# Docker runs it as ENTRYPOINT with the CMD as arguments:
#   docker-entrypoint.sh gunicorn config.asgi:application
#   docker compose run --rm web python manage.py createsuperuser
#     -> docker-entrypoint.sh python manage.py createsuperuser
# So every start of the container goes through migrate + collectstatic first,
# except the Celery containers (see below).
#
# PostgreSQL is already accepting connections here: in docker-compose.yml
# web has depends_on: db: condition: service_healthy, so Docker starts web
# only after the db healthcheck (pg_isready) passes.

# Stop at the first failing command. Without it a failed migrate would be
# ignored and gunicorn would start on a database with a wrong schema.
set -e

# Started as root: only on Railway, with RAILWAY_RUN_UID=0 on the web
# service. Railway mounts its Volume (the covers, /app/media) owned by
# root, and the "app" user of the image (Dockerfile USER app) couldn't
# write uploaded covers there. So as root: give the folder to "app", then
# run THIS script again as "app" (setpriv, from util-linux, is in the
# image) and everything below, the server included, runs without root.
# Locally (docker compose) the container starts as "app": skipped.
# Docs: https://docs.railway.com/reference/volumes
if [ "$(id -u)" = "0" ]; then
    echo "Started as root: chown of the media folder, then running as app"
    chown app:app /app/media
    exec setpriv --reuid=app --regid=app --init-groups "$0" "$@"
fi

# celery worker / celery beat: no migrate, no collectstatic. Three
# containers running migrate at the same moment could apply the same
# migration twice ("relation already exists"); web does it alone, and the
# Celery services start only after web is healthy (depends_on).
# They need no static files either.
if [ "$1" != "celery" ]; then
    echo "Applying database migrations..."
    # --noinput: never ask questions (nobody can answer them in a container)
    python manage.py migrate --noinput

    echo "Collecting static files..."
    # Copies static files of all apps (admin css/js, our static/) to STATIC_ROOT
    # (the static_data volume). Only new or changed files are copied, so later
    # starts take a second.
    python manage.py collectstatic --noinput
fi

echo "Starting: $*"
# exec: replace this shell with the command instead of running it as a child.
# Then gunicorn becomes PID 1 and gets SIGTERM from `docker compose stop`
# itself; otherwise sh would get it, and sh doesn't pass it on, so Docker
# would kill gunicorn after 10 seconds without a clean shutdown.
# "$@": all arguments exactly as given (the CMD), each one kept whole.
exec "$@"
