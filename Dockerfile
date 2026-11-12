# Image for the Django app (the "web" service in docker-compose.yml).
#
# Build:  docker compose build web
# The image holds only code and Python packages. Everything that changes at
# run time lives outside it:
#   - settings and secrets: environment variables (env_file: .env in compose);
#   - database: PostgreSQL container + volume;
#   - static files, covers, logs: volumes mounted over the folders made below.

# Slim = Debian without compilers and docs (about 130 MB instead of 1 GB).
# Enough for us: psycopg[binary] and pillow come as ready wheels with their
# C libraries inside, nothing has to be compiled.
FROM python:3.13-slim

# PYTHONUNBUFFERED=1: print() and logging go to stdout at once, not in
#   blocks; otherwise `docker compose logs` shows lines late or loses them
#   when the container stops.
# PYTHONDONTWRITEBYTECODE=1: no __pycache__/*.pyc files. They would only
#   be written into the container layer and are lost on every restart.
# PIP_NO_CACHE_DIR=1: pip doesn't keep downloaded archives, the image is smaller.
# PIP_DISABLE_PIP_VERSION_CHECK=1: no "new pip version available" request.
# DJANGO_SETTINGS_MODULE: every process of the image (gunicorn, celery,
#   manage.py commands) uses the production settings (config/settings/
#   production.py). Set here, not only in docker-compose.yml, so a hosting
#   that runs the image (Railway) gets them without one more variable.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

# All the next commands (COPY, RUN, CMD) work in /app
WORKDIR /app

# Packages first, in a separate layer. Docker caches every instruction:
# while requirements.txt is unchanged, this slow step (downloading
# packages) is taken from the cache, and a change in the code rebuilds only
# the "COPY . ." layer below.
# requirements.txt only, without requirements-dev.txt: no Debug Toolbar,
# pytest, black or flake8 in the image.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Non-root user: if someone breaks into the app through a vulnerability,
# they get a user with no rights to the system and to the code.
# --system: a service account (no password, no login shell);
# uid 1000 is a fixed number, so file owners in volumes are predictable.
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home app

# The code. It stays owned by root: the app user can read it but not
# change it. Which files are NOT copied: see .dockerignore.
COPY . .

# Folders the app writes to, owned by the app user:
#   staticfiles/ - collectstatic output (STATIC_ROOT), volume static_data
#   media/       - uploaded covers (MEDIA_ROOT), volume media_data
#   logs/        - logs/app.log (LOGGING), base.py creates it on start,
#                  but /app belongs to root, so we create it here.
# When docker compose mounts an EMPTY named volume over such a folder for
# the first time, Docker copies the folder's owner into the volume. That is
# why the folders must exist in the image with the right owner.
RUN mkdir -p staticfiles media logs \
    && chown app:app staticfiles media logs

# From here on, and when the container runs, everything runs as "app"
USER app

# Runs before every command of the container: migrate + collectstatic,
# then `exec` of the CMD below (or of the command given to
# `docker compose run web ...`). See docker-entrypoint.sh.
# It needs the executable bit: git keeps it (chmod +x), COPY . . copies it.
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Documentation only: the app listens on 8000 by default, inside the Docker
# network (browsers reach it through nginx, docker-compose.yml "8000:80").
# A hosting may choose another port with $PORT (gunicorn.conf.py).
EXPOSE 8000

# Default command: gunicorn with uvicorn workers (ASGI). Everything else
# (port from $PORT, workers, proxy headers, ...) is in gunicorn.conf.py,
# which gunicorn reads from the current folder (/app) by itself.
#   config.asgi:application - the `application` object from config/asgi.py
# The exec form ["...", "..."] (not a string): gunicorn becomes process
# PID 1 itself and receives SIGTERM from `docker compose stop` directly,
# so it finishes current requests and exits cleanly.
CMD ["gunicorn", "config.asgi:application"]
