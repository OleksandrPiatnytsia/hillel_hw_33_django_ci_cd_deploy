# Bookstore (Hillel Python Pro homework, ProjectA of the final project)

Context for Claude Code sessions in this repository. Talk to the user in Ukrainian.
The detailed documentation of every feature is in README.md (Ukrainian); this file is the
short map + the rules of work.

## What this is

A Django online bookstore built over the whole course, one repository per homework (each copied
from the previous one). This repository is the last one (CI/CD + deploy) and is now also
**ProjectA of the final homework**: two Django services, the bookstore and Analytics
(`../hillel_hw_34_django_analytics`, its own repository, its own sessions; the full approved
design is in that repository's CLAUDE.md).

Production: Railway, https://web-production-8fd24010.up.railway.app (services web + worker
with embedded beat, PostgreSQL, Redis, a Volume for covers). Deploys from `main` after CI
("Wait for CI").

## Stack

Python 3.13, Django 6.1.3, DRF 3.18.3 + simplejwt + drf-spectacular (Swagger at /api/docs/),
django-filter, PostgreSQL 17 (ICU uk-UA collation), Redis 8 (cache db 0, Celery broker db 1),
Celery 5.7 + beat, gunicorn with the uvicorn worker (async views), nginx (local Docker only),
WhiteNoise (Railway), Stripe, Brevo email via django-anymail, NBU exchange rates, Sentry,
Bootstrap 5.3 + a little vanilla JavaScript (progressive enhancement: everything works without
JavaScript). Languages: uk (default) and en.

## Map

- `config/` — settings package `settings/{base,development,production,test}.py`, `env.py`
  (environment helpers), `celery.py`, `sentry.py`, `version.py` (`__version__`, shown in the
  footer; bump on releases), context processors, middleware.
- Apps: `users` (custom User, groups Managers etc.), `books` (Book, Author, Publisher, Category,
  BookFormat paper/ebook/audio; `books/cache.py` template fragment cache + invalidation),
  `inventory` (warehouses, stock), `cart` (session cart, key = format id), `wishlist`,
  `ratings` (only buyers rate), `orders` (`services.create_order()`, `reports.py` daily email),
  `payments` (Stripe, webhooks), `currencies` (NBU rates, display currency), `api` (the whole
  REST layer).
- `templates/` (base, navbar), `static/` (css/styles.css, js/*.js), `locale/{uk,en}`.
- `tests/` — `unit/`, `integration/`, `api/`, factories in `tests/factories.py`
  (factory-boy). About 856 tests, coverage ~98.9%; the minimum is 70% (pytest.ini).
- `.github/workflows/django.yml` — jobs lint (black, flake8) + test (PostgreSQL service,
  coverage badge pushed to the `badges` branch on main) -> docker (build; push to Docker Hub
  `ufolog/hillel-bookstore` on main).
- `docker-compose.yml` — nginx, web, db, redis, celery, celery-beat, flower, stripe-cli.

## Rules of work (the user's)

- **The user runs** venv / pip, `makemigrations` / `migrate`, git commits and pushes, and every
  state-changing docker command. I only give the commands. Read-only checks are fine.
  I may run tests, black and flake8 myself (`.venv/bin/...`), but in the user's steps write
  plain `python manage.py ...`, `pytest`, `black .`, `flake8`.
- Every answer that needs the user's action ends with a numbered **"Твої кроки"** block:
  migrate -> `docker compose up -d --build` (code is baked into the image, no bind mount) ->
  `pytest` (expected count) -> browser check -> commit command `git commit -am "..."`
  (+ `git add` for new untracked files: migrations, templates, modules).
- Ports on the Mac: Docker nginx http://localhost:8000; runserver must use
  `python manage.py runserver 8001`.
- Branches: feature branch -> PR into `stage` -> PR `stage` -> `main`. Don't work on `main`.
- Code style: black (line-length 100) + flake8 must be clean; comments explain *why*, in plain
  English, without abbreviations (ManyToMany, not M2M).
- Every new user-facing string is translated: `makemessages -l uk -l en`, fill both .po files,
  `compilemessages`; `tests/unit/test_translation_catalog.py` fails on gaps.
- New feature = tests + a README section; README intro lists only the features, no history.
- Scratchpad scripts that boot Django must strip the file log handlers (don't write to `logs/`).
- Review recommendations are presented first; apply only what the user picks.
- New models: the user creates the migrations. For my own test runs before that, use a
  temporary migration module in the scratchpad (MIGRATION_MODULES), never commit it.

## Final project: what is done in THIS repository

Stages of the shared plan that belong to the bookstore:
- **Stage 2 (A's part, done 2026-11-18)**: service `rabbitmq` (rabbitmq:4.4.1-management-alpine,
  hostname rabbitmq, volume hillel_bookstore_rabbitmq_data, ports 127.0.0.1:5672 / 15672,
  login RABBITMQ_USER / RABBITMQ_PASSWORD from .env) and the compose network named
  `bookstore_net`, which Analytics' compose joins as external. Nothing publishes yet.
  At stage 3 add with the publisher code: `rabbitmq_url()` in config/env.py (RABBITMQ_URL or
  RABBITMQ_HOST / PORT / USER / PASSWORD, like Analytics), RABBITMQ_HOST=localhost and
  RABBITMQ_PORT=5672 in .env.example, `RABBITMQ_HOST: rabbitmq` in x-django of the compose.
- **Stage 3**: `OutboxEvent` table written in the same transaction as the order change; a Celery
  task publishes to RabbitMQ (topic exchange `bookstore.events`, publisher confirms, retries);
  events `order.created`, `order.paid`, `order.cancelled` with `event_id` (UUID), `type`,
  `occurred_at` and an order snapshot **without personal data** (customer = hash of the user
  id; amounts also in UAH). RabbitMQ is added to this repository's `docker-compose.yml`
  (Analytics joins this Docker network). No REST fallback for events (the user's decision).
- **Stage 5**: an analytics page for managers that calls Analytics' REST reports with a JWT of a
  service account (Redis cache, a friendly message and logging when Analytics is down); an API
  for the backfill (Analytics pulls old orders once); integration tests.
- The sales part of the daily email to managers (`orders/reports.py`) moves to Analytics;
  the low-stock part stays here.

Present the detailed plan of a stage before coding it.
