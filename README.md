# hillel_hw_33 — CI/CD і деплой

[![CI](https://github.com/OleksandrPiatnytsia/hillel_hw_33_django_ci_cd_deploy/actions/workflows/django.yml/badge.svg?branch=main)](https://github.com/OleksandrPiatnytsia/hillel_hw_33_django_ci_cd_deploy/actions/workflows/django.yml)
![Coverage](https://raw.githubusercontent.com/OleksandrPiatnytsia/hillel_hw_33_django_ci_cd_deploy/badges/coverage.svg)

**Сайт:** https://web-production-8fd24010.up.railway.app/
(стан сервісів: [`/health/`](https://web-production-8fd24010.up.railway.app/health/),
API: [`/api/docs/`](https://web-production-8fd24010.up.railway.app/api/docs/))

Навчальний Django-проєкт (Hillel). Продовження ДЗ №31 (книгарня з REST API,
Redis, Celery, nginx). У цьому ДЗ:

- **GitHub Actions** (`.github/workflows/django.yml`): black і flake8, тести на
  PostgreSQL з покриттям, бейдж покриття без зовнішніх сервісів, Docker-образ
  у Docker Hub після злиття в `main` (див. «CI/CD»);
- **налаштування за середовищами**: пакет `config/settings/` — `base`,
  `development`, `production`, `test`; у production `DEBUG=False`, HTTPS,
  захищені cookies, HSTS, `DATABASE_URL` і `REDIS_URL` (див. «Налаштування»);
- **деплой на Railway**: web (gunicorn + uvicorn), worker (Celery з Beat), Flower,
  PostgreSQL, Redis, Volume для обкладинок; статика через **WhiteNoise**,
  перевірка здоров'я `/health/`; у футері версія сайту і задеплоєний коміт
  (див. «Деплой на Railway»);
- **валюти**: курси НБУ з історією (Celery Beat), ціна формату книги в будь-якій
  валюті, перемикач валюти на сайті, замовлення й оплата Stripe у вибраній
  валюті, валюти в API (див. «Валюти»);
- **панель фільтрів каталогу**: блоки, що згортаються, кілька значень у фільтрі,
  плашки активних фільтрів, оновлення списку без перезавантаження, на телефоні —
  панель збоку (див. «Фільтри каталогу»);
- **характеристики видання**: видавництво (окрема модель, основні українські
  видавництва з міграції), мова, рік видання — у формі, на сторінці книги, у
  фільтрах каталогу й в API (див. «Моделі», «Фільтри каталогу»);
- **формати книг**: одна книга продається як паперова, електронна й аудіокнига,
  кожен формат зі своєю ціною, валютою, обкладинкою й сторінками; ціна «від» у
  каталозі, плитки форматів на сторінці книги, формат змінюється в кошику, склад
  лише в паперового, формати в замовленнях і в API (`/api/formats/`)
  (див. «Формати книг»);
- єдиний стиль коду: black + flake8 (`pyproject.toml`, `.flake8`), перевіряються
  ще до коміту хуком pre-commit (`.pre-commit-config.yaml`);
- 786 тестів, покриття 98.89%.

## Стек

- Python 3.13, Django 6.1
- PostgreSQL 17 (`psycopg` 3), Redis 8 (вбудований у Django `RedisCache`)
- Docker, docker compose; gunicorn + uvicorn (ASGI); nginx 1.30 (static, media, проксі — локально)
- WhiteNoise 6.12: статика на Railway, де немає nginx
- GitHub Actions (CI/CD), Docker Hub (образ), Railway (хостинг)
- black 26.10 і flake8 7.5 (`requirements-dev.txt`): стиль коду, перевіряється в CI
  і хуком pre-commit 4.7 перед кожним комітом
- Celery 5.7 (брокер Redis), Celery Beat (розклад у `config/settings/base.py`), Flower 2.2
- Sentry (`sentry-sdk` 2.74): інтеграції Django, Celery, logging
- `psycopg-pool`: пул з'єднань з базою
- gettext (`makemessages` / `compilemessages`), Django i18n
- Django REST Framework 3.18: djangorestframework-simplejwt (JWT), django-filter,
  drf-spectacular (OpenAPI, Swagger UI, ReDoc), django-cors-headers
- Bootstrap 5.3 (через CDN, із перевіркою `integrity`)
- Pillow: перевірка зображень для `ImageField`
- python-dotenv: налаштування з `.env`
- Stripe: `stripe` 16 (Checkout Session, перевірка підпису webhook), Stripe CLI 1.55 у Docker
- Gmail SMTP через `MAILERS` (новий формат налаштувань пошти в Django 6.1);
  django-anymail 15.2: Brevo HTTP API на Railway
- django-debug-toolbar 8.0 (тільки для розробки, `requirements-dev.txt`)
- Тести (`requirements-dev.txt`): pytest 9, pytest-django, pytest-asyncio, pytest-cov,
  factory-boy, polib

## AI Usage

Інструмент — **Claude Code** (модель Claude Opus 5.5) у терміналі: читає код,
змінює файли, запускає тести. Команди, які змінюють середовище (`pip`,
`git commit`, `docker compose`, міграції), виконувалися вручну.

Які промпти використовувалися (повний текст — у [`AI_PROMPTS.md`](AI_PROMPTS.md)):

1. **Головний:** умова ДЗ + «треба взяти по мінімуму те чого ми не робили…
   проведи аналіз, запропонуй план виконання». AI порівняв умову з тим, що вже
   було в проєкті, і запропонував план з 4 етапів; план затверджено.
2. **Code review**, один шаблон для трьох views: коректність, безпека,
   SQL-запити, читабельність; для кожної проблеми — сценарій і виправлений код.
3. **Тести моделей:** знайти непокриті рядки `Book`, `Order`, `Payment`,
   написати на них тести з фабриками, очікувані значення брати з коду,
   позначити кожен тест `# Generated with AI, reviewed and modified`.
4. **Docstrings:** для views без них — метод і адреса, хто викликає,
   обмеження, куди перенаправляє; кнопки звірити з шаблонами.
5. **Документація:** README, `AI_PROMPTS.md`, `COVERAGE.md`; цифри тільки з
   реального запуску `pytest`.

| Що | Як | Результат |
|---|---|---|
| Code review | один промпт для трьох view: коректність, безпека, SQL-запити, читабельність | [`AI_REVIEW.md`](AI_REVIEW.md): початковий код → рекомендації → рішення → фінальний код |
| Тести | AI шукає непокриті рядки моделей і пише тести на них | `tests/unit/test_models.py`: 3 нові тести, моделі на 100% |
| Документація | docstrings для `cart_remove`, `cart_clear`, `order_detail`, `order_cancel` | адреса, метод, що робить view і куди перенаправляє |

Прийняті рекомендації рев'ю:

- `checkout`: `@require_http_methods(["GET", "POST"])` — на PUT / PATCH / DELETE
  тепер 405 замість сторінки з формою;
- `BookListView`: неправильний параметр (`?category=<видалена>`) показує помилку,
  а решта фільтрів працює, замість усього каталогу; при «ціна від > ціни до»
  ігноруються лише ціни; `pk` завжди останній у сортуванні (стабільні сторінки);
- `order_status`: замовлення і сума успішних платежів — один SQL-запит
  (`annotate(Sum(..., filter=Q(...)))`) замість двох.

Як перевірявся результат AI:

- кожну рекомендацію рев'ю приймав або відхиляв я, а не AI;
- кожна зміна в коді має тест, увесь набір (212 тестів) проходить;
- твердження в документах AI звіряв з кодом (дві неточності знайдено й виправлено,
  див. [`AI_PROMPTS.md`](AI_PROMPTS.md)).

## Сторінки сайту

| URL | Ім'я маршруту | View | Доступ | Що робить |
|---|---|---|---|---|
| `/` | `books:list` | `BookListView` | усі | каталог: панель фільтрів, плашки, сортування, 12 / 24 / 48 книг на сторінці |
| `/<pk>/` | `books:detail` | `BookDetailView` | усі | сторінка книги з блоком «Характеристики» |
| `/create/` | `books:create` | `BookCreateView` | `books.add_book` | додавання книги |
| `/<pk>/update/` | `books:update` | `BookUpdateView` | `books.change_book` | редагування книги |
| `/<pk>/delete/` | `books:delete` | `BookDeleteView` | `books.delete_book` | підтвердження й видалення; книга в замовленнях не видаляється (`PROTECT`): попередження замість кнопки, «залишок 0» для зняття з продажу |
| `/authors/` | `books:author_list` | `AuthorListView` | усі | автори з кількістю книг |
| `/authors/<pk>/` | `books:author_detail` | `AuthorDetailView` | усі | автор, біографія та його книги |
| `/search/?q=` | `books:search` | `book_search` (**async**) | усі, GET | JSON: до 8 книг для підказок пошуку |
| `/accounts/login/` | `users:login` | `UserLoginView` | усі | вхід (за username) |
| `/accounts/logout/` | `users:logout` | `UserLogoutView` | POST | вихід |
| `/accounts/signup/` | `users:signup` | `SignUpView` | гості | реєстрація |
| `/accounts/profile/` | `users:profile` | `ProfileView` | залогінені | дані доставки, групи й права поточного користувача |
| `/accounts/profile/edit/` | `users:profile_edit` | `ProfileEditView` | залогінені | ім'я, телефон, адреса доставки |
| `/cart/` | `cart:detail` | `cart_detail` | усі | кошик |
| `/cart/add/<book_id>/` | `cart:add` | `cart_add` | POST | додати книгу або задати кількість (`override`) |
| `/cart/remove/<book_id>/` | `cart:remove` | `cart_remove` | POST | прибрати книгу з кошика |
| `/cart/clear/` | `cart:clear` | `cart_clear` | POST | очистити кошик |
| `/orders/` | `orders:list` | `OrderListView` | залогінені | My orders: власні замовлення, по 20 |
| `/orders/checkout/` | `orders:checkout` | `checkout` | залогінені | форма доставки й створення замовлення у валюті перемикача |
| `/orders/<pk>/` | `orders:detail` | `order_detail` | власник (інакше 404) | замовлення, кнопки Pay і Cancel |
| `/orders/<pk>/cancel/` | `orders:cancel` | `order_cancel` | POST, власник | скасувати нове неоплачене замовлення |
| `/orders/<pk>/status/` | `orders:status` | `order_status` (**async**) | власник (401 / 404 у JSON) | JSON: статус замовлення й оплати |
| `/payments/pay/<order_id>/` | `payments:pay` | `pay` | POST, власник | на сторінку оплати Stripe |
| `/payments/success/` | `payments:success` | `payment_success` | залогінені | повернення зі Stripe, `?session_id=...` |
| `/payments/cancelled/<payment_id>/` | `payments:cancelled` | `payment_cancelled` | залогінені | «назад» зі Stripe |
| `/payments/webhook/<provider>/` | `payments:webhook` | `webhook` | POST, підпис Stripe | події від Stripe |
| `/admin/` | `admin:index` | | `is_staff` | адмінка |
| `/health/` | `health` | `health` (**async**, `config/views.py`) | усі, GET | стан PostgreSQL і Redis: 200 або 503, JSON |
| `/i18n/setlang/` | `set_language` | `set_language` (`config/views.py`) | POST | змінити мову: cookie + `User.language` |
| `/currency/` | `set_currency` | `set_currency` (`currencies/views.py`) | POST | змінити валюту цін: код у сесії, назад на `next` |
| `/currencies/rates/` | `currencies:rates` | `NBURatesView` | право додавати й змінювати курси | курси НБУ: подивитися, виправити, зберегти кнопкою |
| `/__debug__/` | | | `DEBUG` + `INTERNAL_IPS` | службові адреси Debug Toolbar |

Маршрути описані в `urls.py` кожного застосунку (`app_name` = `books`, `users`,
`cart`, `orders`, `payments`) і підключені в `config/urls.py` через `include()`. У шаблонах і коді адреси
будуються тільки за іменами: `{% url 'books:detail' book.pk %}`,
`reverse_lazy("books:list")`.

## REST API

API для зовнішніх клієнтів (мобільний застосунок, фронтенд на іншому домені,
інший сервіс). Окремий застосунок `api/` без власних моделей: серіалізатори,
ViewSets і права працюють з моделями `books` і `orders` і викликають ті самі
сервіси, що й сайт (`create_order()`, `cancel_order()`). Правила — одні.

Документація: **http://localhost:8000/api/docs/** (Swagger UI, можна
виконувати запити), `/api/redoc/` (для читання), `/api/schema/` (OpenAPI 3, YAML).

### Адреси

| Метод і URL | Хто | Що робить |
|---|---|---|
| `GET /api/` | усі | список розділів API |
| `POST /api/token/` | усі, 10/хв | `username` + `password` → `access` + `refresh` |
| `POST /api/token/refresh/` | усі | `refresh` → новий `access` |
| `POST /api/token/verify/` | усі | чи дійсний токен (200 / 401) |
| `GET /api/books/`, `/api/books/<id>/` | усі | книги з вкладеними автором, категоріями й форматами в продажу; `display_price` — ціна «від»; `?currency=USD` → у доларах |
| `POST /api/books/` | `books.add_book` (Editors, Managers) | нова книга (без форматів вона не продається) |
| `PUT`, `PATCH /api/books/<id>/` | `books.change_book` | змінити книгу |
| `DELETE /api/books/<id>/` | `books.delete_book` (Managers) | видалити; книга в замовленнях → 409 |
| `GET /api/formats/[<id>/]` | усі (зняті з продажу — лише Editors, Managers) | формати книг; `?book=<id>`, `?format_type=`, `?is_active=` |
| `POST`, `PUT`, `PATCH`, `DELETE /api/formats/<id>/` | `books.add/change/delete_bookformat` (Editors, Managers) | формат: ціна, валюта, обкладинка, сторінки, «у продажу»; `stock` паперового — лише з `inventory.change_stock`; останній формат або формат у замовленнях → 409 |
| `GET /api/authors/[<id>/]`, `/api/publishers/[<id>/]`, `/api/categories/[<id>/]` | усі | автори, видавництва й категорії з `books_count` |
| `POST`, `PUT`, `PATCH`, `DELETE` авторів, видавництв і категорій | `IsAdminUser` (`is_staff`) **і** право моделі | як в адмінці; є книги → 409 на `DELETE` |
| `GET /api/currencies/`, `/api/currencies/<code>/` | усі | валюти, які пропонує магазин, з курсом НБУ на сьогодні |
| `GET /api/orders/` | залогінені | свої замовлення; персонал (`is_staff`) — усі |
| `POST /api/orders/` | залогінені | нове замовлення одразу з позиціями; необов'язковий заголовок `Idempotency-Key` |
| `GET /api/orders/<id>/` | власник або персонал | чуже для клієнта → 404 |
| `POST /api/orders/<id>/cancel/` | лише власник | скасувати нове неоплачене; чуже замовлення для персоналу → 403, вже скасоване або оплачене → 409 |
| `/api/auth/login/` | усі | вхід для browsable API (HTML-сторінки `/api/...` у браузері) |

`PUT` / `PATCH` / `DELETE` замовлень немає (405): статус змінює менеджер в адмінці,
статус оплати — платежі.

### Автентифікація: JWT і сесія

```python
# config/settings/base.py
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",  # Authorization: Bearer <access>
        "rest_framework.authentication.SessionAuthentication",        # cookie входу на сайт
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],  # закрито за замовчуванням
    ...
}
SIMPLE_JWT = {"ACCESS_TOKEN_LIFETIME": timedelta(minutes=15), "REFRESH_TOKEN_LIFETIME": timedelta(days=1)}
```

```bash
# 1. токени
curl -X POST http://localhost:8000/api/token/ -H "Content-Type: application/json" \
     -d '{"username": "ann", "password": "..."}'
# {"refresh": "eyJ...", "access": "eyJ..."}

# 2. запит з access-токеном
curl http://localhost:8000/api/orders/ -H "Authorization: Bearer eyJ..."

# 3. через 15 хвилин access прострочено (401) -> новий без пароля
curl -X POST http://localhost:8000/api/token/refresh/ -H "Content-Type: application/json" \
     -d '{"refresh": "eyJ..."}'
```

- Токен підписаний `SECRET_KEY` (HS256) і містить `user_id` і термін дії; база
  на кожен запит не потрібна для перевірки підпису, лише щоб завантажити користувача.
- Сесія — для Swagger і browsable API в браузері: хто увійшов на сайт, той
  увійшов і в API. Для `POST` / `PATCH` / `DELETE` сесія вимагає CSRF-токен,
  тому чужий сайт не може скористатися cookie відвідувача.
  **Тому в Swagger, відкритому в браузері з входом на сайт, запити йдуть від
  цього користувача** навіть без «Authorize»; перевіряти JWT — у вікні інкогніто.
- Невдалий вхід логується сигналом `user_login_failed` (`users/signals.py`):
  simplejwt викликає `authenticate()`. Успішний — рядком `API token issued`.

### Права доступу

```python
# api/views/catalog.py
class BookViewSet(LoggedModelViewSet):
    permission_classes = [DjangoModelPermissionsOrAnonReadOnly]
    # GET — усім; POST -> add_book, PUT/PATCH -> change_book, DELETE -> delete_book

class StaffWriteMixin:                     # AuthorViewSet, PublisherViewSet, CategoryViewSet
    def get_permissions(self):            # окремі права для читання й запису
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdminUser(), DjangoModelPermissions()]   # is_staff І право групи — як в адмінці

# api/views/orders.py
class OrderViewSet(...):
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
```

- **`IsOwnerOrReadOnly`** (`api/permissions.py`) — власний клас: читати може
  кожен, хто отримав об'єкт, змінювати — лише власник (`obj.user_id == request.user.pk`).
  *Що* бачить користувач, вирішує `get_queryset()`: клієнт — свої замовлення
  (чуже → 404, а не 403, щоб не підказувати, що таке замовлення існує),
  персонал — усі. Тому менеджер читає будь-яке замовлення, але `cancel` чужого → 403.
- **`IsAdminUser`** (DRF) пропускає лише `is_staff`. Сам по собі він дозволив би
  будь-якому співробітнику видаляти категорії, тому поруч `DjangoModelPermissions`:
  `is_staff` відчиняє двері, група вирішує, що можна (Managers видаляють категорію,
  редактор має `add_author`, але не `is_staff`). `get_permissions()` замість
  `permission_classes`, бо читання відкрите всім, а `IsAdminUser` не має варіанта «або лише читання».
- **Залишок (`stock`)** паперового формату — як в адмінці: без `inventory.change_stock` змінити його
  не можна (403). Надіслати *поточне* значення можна: клієнт, що робить `PUT`
  з усіма прочитаними полями, не отримає помилку.
- Анонім на запис отримує **401** (з токеном запит міг би пройти), залогінений
  без права — **403**.

### Серіалізатори: читання вкладене, запис через id

```json
GET /api/books/7/
{"id": 7, "title": "Kobzar",
 "author": {"id": 3, "name": "Taras Shevchenko"},
 "categories": [{"id": 1, "name": "Poetry", "slug": "poetry"}],
 "display_price": "149.00", "display_currency": "UAH", "in_stock": true,
 "publisher": {"id": 12, "name": "Фоліо"}, "language": "uk", "publication_year": 2017,
 "formats": [
   {"id": 11, "format_type": "paper", "format_type_display": "Паперова",
    "price": "350.00", "currency": "UAH", "cover_type": "hard", "pages": 224,
    "is_active": true, "stock": 4, "in_stock": true, ...},
   {"id": 12, "format_type": "ebook", "price": "149.00", "stock": null, "in_stock": true, ...}],
 "cover": "http://localhost:8000/media/covers/2026/11/kobzar.jpg", ...}

POST /api/books/
{"title": "Kobzar", "author_id": 3, "category_ids": [1], "publisher_id": 12, "language": "uk"}
```

```python
class BookSerializer(serializers.ModelSerializer):
    author = AuthorShortSerializer(read_only=True)                       # читання: об'єкт
    author_id = serializers.PrimaryKeyRelatedField(source="author",      # запис: id
                                                   queryset=Author.objects.all(), write_only=True)
    formats = BookFormatInBookSerializer(source="active_formats", many=True, read_only=True)
```

Ціни — рядки (`"350.00"`), а не числа: так у JSON не губляться копійки на округленні float.
`display_price` книги — найдешевший формат у продажу у валюті `?currency=`, як «від» у
картці сайту; за ним працюють `?price_min=`, `?price_max=` і `?ordering=price`.

### Формати: окремий ресурс `/api/formats/`

Ціна, валюта, тип, обкладинка, сторінки й залишок належать формату, а не книзі.
**Рішення**: формати пишуться окремим ресурсом, а в книзі вони лише для читання.
Вкладений запис (`"formats": [...]` у `PUT` книги) потребував би власних
`create()` / `update()`, а пропущений рядок означав би «видалити формат», що
ламається на форматі з замовлень.

```json
POST /api/formats/
{"book_id": 7, "format_type": "ebook", "price": "149.00", "currency": "UAH"}

PATCH /api/formats/11/
{"price": "320.00", "stock": 10}
```

- `book_id` і `format_type` задаються лише під час створення: на тип посилаються
  рядок складу й копія типу в замовленнях. Інший тип — новий формат.
- `BookFormatSerializer.validate()` повторює `BookFormat.clean()` (обкладинка лише
  в паперового, сторінки не в аудіокниги) і перевіряє «один формат типу на книгу».
- `stock` — лише в паперового формату; для файлу у відповіді `null`.
- `DELETE`: формат із замовлень (`on_delete=PROTECT`) або останній формат книги → **409**;
  зняти з продажу — `{"is_active": false}`.

### Замовлення без кошика

Кошика в API немає — **рішення**: кошик — це частина інтерфейсу сайту (сесія
відвідувача між сторінками), а клієнт API надсилає вже готове замовлення.
Кошик сайту й далі живе в сесії.

```json
POST /api/orders/
{"full_name": "Ann Shevchenko", "phone": "+380 67 123 45 67", "address": "Kyiv, Khreshchatyk 1",
 "currency": "USD",
 "items": [{"format_id": 12, "quantity": 2}, {"book_id": 9, "quantity": 1}]}
```

Рядок замовлення називає **формат** (`format_id`). `book_id` дозволено лише для
книги з одним форматом у продажу; якщо їх кілька — **400** з переліком форматів:
API не обирає формат за клієнта. У відповіді кожна позиція має
`"format": {"id": 12, "format_type": "ebook", "format_type_display": "Електронна"}`.

`currency` — необов'язкова, типово `UAH`; код з `/api/currencies/`, інший → 400.

1. `OrderCreateSerializer` перевіряє запит; позиції — вкладений
   `OrderItemCreateSerializer(many=True)`: формат існує й у продажу, `quantity >= 1`,
   один формат — один рядок. Телефон — та сама `normalize_phone()`, що на сайті.
2. `create_order()` — та сама функція, що на сайті: блокування книг
   (`select_for_update`), перевірка залишку, ціни з каталогу, резерв лише паперових
   примірників, лист після COMMIT.
3. Не вистачає примірників → **400** `{"items": ["«Kobzar»: залишився лише 1 примірник, а ви замовили 3."]}`,
   нічого не збережено.
4. **201** — замовлення у форматі `GET /api/orders/<id>/`.

Ціни, сума й статуси з запиту не беруться (`"total": "1.00"` проігнорується).
У відповіді — `currency` і `exchange_rate` замовлення, а в позиціях `price` у валюті
замовлення та `original_price` + `original_currency` книги. Той самий
`Idempotency-Key` з іншою валютою — 422.
Оплата — на сайті: у відповіді є `site_url`, сторінка замовлення з кнопкою «Pay»
(Stripe Checkout — сторінка для людини).

### `Idempotency-Key`: повторний запит — те саме замовлення

Клієнт надіслав `POST /api/orders/`, а відповідь не дійшла (тайм-аут, обрив
мережі). Чи створено замовлення — невідомо, і клієнт надсилає запит ще раз.
Без захисту це друге замовлення й ще раз зарезервовані книги. З заголовком
`Idempotency-Key` (будь-який унікальний текст, наприклад UUID, новий для
кожного нового замовлення):

| Запит | Відповідь |
|---|---|
| перший з ключем | **201**, нове замовлення; ключ зберігається в `Order.idempotency_key` |
| той самий ключ і те саме тіло | **201**, **те саме** замовлення + заголовок `Idempotent-Replayed: true`; нічого не створюється й не резервується, другого листа немає |
| той самий ключ, інші формати чи адреса | **422**: ключ скопійовано замість нового — помилка клієнта |
| запит не вдався (400, не вистачає книг) | нічого не збережено, ключ теж: його можна надіслати знову |
| без заголовка | як раніше, кожен запит — нове замовлення |

«Те саме тіло» порівнюється так, як запит називає позиції: рядок `format_id` — з
форматом позиції замовлення, рядок `book_id` — з її книгою
(`OrderCreateSerializer.same_items()`). Формат для `book_id` обирається заново й
міг змінитися між запитами, а книга та сама.

```python
# orders/models.py — унікальність у базі, а не лише перевірка в коді
models.UniqueConstraint(
    fields=["user", "idempotency_key"],
    condition=~models.Q(idempotency_key=""),   # замовлення без ключа (сайт) не обмежуються
    name="orders_order_unique_idempotency_key_per_user",
)
```

```python
# api/views/orders.py, OrderViewSet.create()
if key and (existing := self._order_by_key(key)) is not None:
    return self._replay(existing, serializer)        # звичайний повтор: 201 + Idempotent-Replayed / 422
try:
    order = create_order(..., idempotency_key=key)
except IntegrityError:                               # два запити одночасно: обидва не знайшли ключ,
    existing = self._order_by_key(key) if key else None   # перший закомітив, INSERT другого
    if existing is None:                             # порушив унікальний індекс -> ROLLBACK
        raise                                        # інше обмеження — справжня помилка (500)
    return self._replay(existing, serializer)
```

- **Чому в базі, а не в Redis.** Замовлення і його ключ записуються в одній
  транзакції: або обидва, або нічого. Два одночасні запити зупиняє унікальний
  індекс PostgreSQL (другий `INSERT` чекає на COMMIT першого й отримує помилку),
  а не перевірка в Python, яку обидва пройшли б одночасно.
- **Те саме тіло** — ті самі книги й кількості та ті самі дані доставки після
  очищення серіалізатором (`+380 67 123 45 67` і `+380671234567` однакові).
  У відповіді — поточний стан замовлення: повтор після оплати покаже `paid`.
- **Ключі окремі для кожного користувача.** Ключ ніде не видаляється: це текст до
  255 символів у рядку замовлення.
- Тест `test_two_simultaneous_requests_with_the_same_key_make_one_order`
  надсилає два запити з двох потоків одночасно (справжні COMMIT): одне
  замовлення, обидві відповіді 201, одна з них `Idempotent-Replayed`.
- Для фронтенду на іншому домені `idempotency-key` додано в
  `CORS_ALLOW_HEADERS`, а `Idempotent-Replayed` — у `CORS_EXPOSE_HEADERS`:
  інакше браузер не надішле заголовок і не покаже JavaScript відповідь з ним.

### Пагінація, фільтри, пошук, сортування

- Усі списки — по **20**: `{"count": 135, "next": ".../?page=2", "previous": null, "results": [...]}`.
- Книги (`api/filters.py`, `BookFilter` з django-filter — ті самі, що на сторінці каталогу,
  успадковані з `books/filters.py`): `?category=<slug>`, `?author=<id>`, `?publisher=<id>`,
  `?language=uk|en|pl|de|fr|es`, `?book_type=paper|ebook|audiobook`,
  `?cover_type=hard|soft|dust_jacket` (усі можна повторювати: `?author=1&author=5` — «або»),
  `?year_min=`, `?year_max=`, `?price_min=`, `?price_max=`, `?stock=in_stock|low|out`.
  Видавництво без книг API приймає (порожній список), а не 400, як сайт.
- **Валюта книг**: у кожної книги `price` + `currency` (її власна ціна) і
  `display_price` + `display_currency` — ціна у валюті `?currency=` (типово UAH) за
  курсом НБУ на сьогодні, як на сайті з перемикачем. `?price_min=`, `?price_max=` і
  `?ordering=price` працюють саме з `display_price`, тож книги в різних валютах
  порівнюються правильно; книги без курсу (`display_price: null`) — в кінці.
  Валюта, якої немає в `/api/currencies/`, → 400.
  Неправильне значення → 400 з помилкою параметра (сайт такі ігнорує й показує
  підказку; для програми це помилка в її коді).
- `?search=kobz` — у назві й імені автора; `?ordering=-price` (`title`, `price`,
  `created_at`, `author__name`). `StableOrderingFilter` додає `pk` останнім:
  книги з однаковою ціною не перескакують між сторінками.
- Замовлення: `?status=`, `?payment_status=`, `?currency=`, `?ordering=total`.
- Кількість SQL-запитів не залежить від розміру сторінки: книги — 3, замовлення — 4
  (`select_related`, `prefetch_related`, `annotate(Sum(...))`); перевіряється тестами.

### Throttling, CORS, помилки

```python
"DEFAULT_THROTTLE_RATES": {"anon": "100/hour", "user": "1000/hour", "token": "10/minute"},
CORS_ALLOWED_ORIGINS = [... з .env ...]
CORS_URLS_REGEX = r"^/api/.*$"
```

- **Throttling**: анонім — за IP, користувач — за id; `/api/token/` окремо 10 на
  хвилину (кожен запит — перевірка пароля). Лічильники в кеші (Redis). Понад
  ліміт — **429** і заголовок `Retry-After`.
- **CORS** (`django-cors-headers`): браузер дозволить JavaScript з
  `http://localhost:3000` прочитати відповідь API, лише якщо цей origin є в
  `CORS_ALLOWED_ORIGINS`. Тільки для `/api/`: сторінки сайту закриті для інших
  доменів. curl, Postman і сервери CORS не перевіряють.
- **Коди**: 400 — неправильні дані (помилки по полях), 401 — немає або
  недійсний токен, 403 — немає права, 404, 405 — дія не підтримується,
  **409 Conflict** — запит правильний, але стан даних не дозволяє: видалити книгу
  з замовлень, автора чи категорію з книгами (`on_delete=PROTECT`), скасувати
  оплачене замовлення. 422 — `Idempotency-Key` уже використаний для іншого
  замовлення. 429 — ліміт.
- Тексти помилок — мовою запиту (`Accept-Language: en`), за замовчуванням українською.

### Документація (drf-spectacular)

Схему OpenAPI drf-spectacular будує з коду: адреси, серіалізатори (поля й типи),
фільтри. Описи для клієнта — `extend_schema` в `api/docs.py`, бо docstrings у
коді написані для розробника; хук `remove_component_descriptions` прибирає їх і
з розділу «Schemas». `manage.py spectacular --validate --fail-on-warn` проходить
без попереджень.

## Структура

```
.github/
├── workflows/django.yml     # CI/CD: lint -> test -> docker (див. «CI/CD»)
└── scripts/coverage_badge.py  # coverage.xml -> coverage.svg для гілки badges
config/
├── settings/                # див. «Налаштування»
│   ├── base.py              # спільне: PostgreSQL, Redis, кеш, Celery і розклад Beat, Sentry, LOGGING
│   ├── development.py       # runserver: DEBUG, Debug Toolbar (типово для manage.py)
│   ├── production.py        # Docker і Railway: без DEBUG, HTTPS, WhiteNoise (типово для asgi/wsgi/celery)
│   └── test.py              # pytest: швидкий хеш паролів, LocMemCache, без файлу логів
├── version.py               # __version__ (вручну) і deployed_commit() (від Railway)
├── context_processors.py    # app_version і app_commit для футера
├── env.py                   # env_bool(), env_list(), DATABASE_URL або POSTGRES_*, redis_url()
├── uvicorn_worker.py        # воркер gunicorn: uvicorn без подій lifespan
├── urls.py                  # admin + books + accounts/ + cart/ + orders/ + payments/ + api/ + health/ + sentry-debug/ + i18n/
├── celery.py                # Celery-застосунок, enqueue_on_commit() (задача після COMMIT)
├── sentry.py                # init_sentry(): що відправляється в Sentry, а що ні
├── asgi.py                  # ASGI-застосунок (Docker: gunicorn + uvicorn)
├── views.py                 # health (async), set_language, sentry_debug
├── i18n.py                  # is_supported_language(), set_language_cookie()
├── middleware.py            # RequestTimingMiddleware (sync + async)
└── logging_filters.py       # HideClientErrorTraceback (403/404 без traceback)
users/
├── models.py                # User(AbstractUser): email lowercase і унікальний; phone, address
├── forms.py                 # LoginForm, SignUpForm, ProfileForm (+ Bootstrap-класи)
├── phone.py                 # normalize_phone(): спільна перевірка телефону
├── views.py                 # UserLoginView, UserLogoutView, SignUpView, ProfileView, ProfileEditView
├── urls.py                  # app_name = "users"
├── admin.py                 # UserAdmin з email на сторінці «Add user»
├── signals.py               # логування входу, виходу й невдалих спроб
├── tasks.py                 # clear_expired_sessions (Celery Beat)
├── tools.py                 # admin_tools(): блок «Інструменти» профілю
├── apps.py                  # підключення сигналів у ready()
├── migrations/
│   ├── 0001_initial.py
│   ├── 0002_lowercase_email.py    # дані → lowercase + CheckConstraint
│   ├── 0003_create_groups.py      # групи Customers / Editors / Managers
│   ├── 0004_user_address_user_phone.py
│   ├── 0005_user_language.py      # мова користувача (листи, вхід з іншого пристрою)
│   └── 0006_publisher_permissions.py  # права на видавництва для груп
└── templates/users/
    ├── auth_form.html       # спільний для входу й реєстрації
    ├── profile.html
    └── profile_edit.html
books/
├── models.py                # Category, Author, Publisher, Book (+ cover, характеристики), BookCategory, BookQuerySet
├── filters.py               # BookFilter (спільний з API), CatalogFilter: фільтри, плашки
├── forms.py                 # BookForm (блок «Характеристики»: DETAIL_FIELDS), CoverInput
├── views.py                 # Class-Based Views для книг і авторів, book_search (async)
├── urls.py                  # app_name = "books"
├── admin.py                 # адмінка (+ мініатюри обкладинок, StockInline)
├── cache.py                 # get_cached_book(), invalidate_books(): кеш книги й фрагментів
├── signals.py               # зміна книги, автора, видавництва, категорії -> очищення кешу
├── templates/books/
│   ├── book_list.html
│   ├── book_detail.html
│   ├── book_form.html             # спільний для Create і Update
│   ├── book_confirm_delete.html
│   ├── author_list.html
│   ├── author_detail.html
│   ├── includes/stock_badge.html  # бейдж наявності
│   ├── includes/book_details.html # «Характеристики» на сторінці книги
│   ├── includes/book_form_field.html  # одне поле форми книги
│   ├── includes/filter_section.html, price_filter.html, year_filter.html  # блоки панелі фільтрів
│   └── widgets/cover_input.html   # поле обкладинки з прев'ю
└── management/commands/
    ├── seed_books.py
    └── book_stats.py
currencies/                  # валюти й курси, див. «Валюти»
├── models.py                # Currency, ExchangeRate (історія курсів)
├── nbu.py                   # fetch_rates(): запит до API НБУ
├── services.py              # current_rates() (кеш), convert(), price_in() (SQL), update_rates()
├── display.py               # валюта перемикача (сесія), format_money(), book_price()
├── views.py                 # set_currency: перемикач у навбарі; NBURatesView: курси НБУ з підтвердженням
├── forms.py                 # ConfirmRatesForm: поле на кожну валюту + підписана відповідь НБУ
├── urls.py                  # /currencies/rates/ (namespace "currencies")
├── templates/currencies/rates.html
├── context_processors.py    # display_currency і currency_choices у шаблонах
├── templatetags/money.py    # {% book_price book_format %}, {% price_from book %}, |money:currency
├── tasks.py                 # update_exchange_rates (Celery Beat)
├── signals.py               # зміна курсу чи валюти -> очищення кешу
├── admin.py                 # валюти з поточним курсом, історія курсів
├── migrations/0002_create_currencies.py   # UAH, USD, EUR
└── management/commands/update_exchange_rates.py
inventory/                   # склад, див. «Склад»
├── models.py                # Warehouse, Stock
├── services.py              # set_stock(), return_to_stock()
├── signals.py               # нова книга -> рядок Stock з 0
├── admin.py                 # склади, залишки (list_editable)
└── migrations/              # 0002: Book.stock -> Stock; 0003: право inventory.change_stock
cart/
├── cart.py                  # Cart: кошик у сесії
├── forms.py                 # CartAddForm (quantity, override)
├── views.py                 # cart_detail, cart_add, cart_remove, cart_clear
├── context_processors.py    # "cart" у кожному шаблоні (лічильник у навбарі)
└── templates/cart/cart_detail.html
orders/
├── models.py                # Order, OrderItem; paid_amount, amount_due, refresh_payment_status()
├── services.py              # create_order(), cancel_order(): транзакції й блокування
├── forms.py                 # CheckoutForm
├── views.py                 # checkout, OrderListView, order_detail, order_cancel, order_status (async)
├── emails.py                # send_order_email(): лист мовою отримувача
├── tasks.py                 # листи, cancel_unpaid_orders, send_daily_report (Celery)
├── reports.py               # щоденний звіт: 3 CSV-файли менеджерам
├── admin.py                 # OrderAdmin: inline позицій і платежів, скасування
├── migrations/0002_managers_order_permissions.py   # права групи Managers
├── management/commands/cancel_unpaid_orders.py
└── templates/orders/        # checkout, order_detail, order_list, includes/, emails/
payments/
├── models.py                # Payment
├── services.py              # ручні платежі, start_online_payment(), webhook-статуси
├── providers/
│   ├── base.py              # PaymentProvider: контракт провайдера
│   ├── stripe_checkout.py   # StripeProvider: Checkout Session, webhook
│   ├── manual.py            # ManualProvider: платежі від менеджера
│   └── registry.py          # "stripe" / "manual" -> об'єкт провайдера
├── views.py                 # pay, payment_success, payment_cancelled, webhook
├── emails.py                # лист «payment received»
├── tasks.py                 # той самий лист як задача Celery
├── admin.py                 # inline для замовлення, список платежів
└── templates/payments/      # payment_success, emails/
api/                         # REST API (без моделей), див. «REST API»
├── urls.py                  # router + токени + документація, namespace "api"
├── views/
│   ├── auth.py              # токени з throttling, публічний корінь /api/
│   ├── catalog.py           # BookViewSet, AuthorViewSet, PublisherViewSet, CategoryViewSet (+ лог, 409, StaffWriteMixin, кеш)
│   ├── currencies.py        # CurrencyViewSet: /api/currencies/
│   └── orders.py            # OrderViewSet: list, retrieve, create, cancel
├── serializers/
│   ├── catalog.py           # вкладені автор, видавництво й категорії, *_id для запису, характеристики, stock, currency, display_price
│   ├── currencies.py        # валюта з курсом
│   └── orders.py            # OrderSerializer, OrderCreateSerializer з позиціями
├── permissions.py           # IsOwnerOrReadOnly
├── filters.py               # BookFilter, StableOrderingFilter
├── exceptions.py            # Conflict (409)
├── cache.py                 # cache_api_response: cache_page з номером покоління
├── signals.py               # зміна каталогу -> нове покоління кешу API
└── docs.py                  # описи для Swagger (extend_schema), хук схеми
templates/                   # спільні шаблони проєкту
├── base.html
├── 403.html                 # «Access denied»
├── 404.html                 # «Page not found» (лише при DEBUG=False)
├── 500.html                 # «Server error»: окремий, без base.html
└── includes/
    ├── navbar.html
    ├── messages.html
    └── pagination.html
locale/                      # переклади (у git разом з .mo: у Docker-образі немає gettext)
├── uk/LC_MESSAGES/django.po # українські переклади (джерело)
├── uk/LC_MESSAGES/django.mo # скомпільовані (їх читає Django)
└── en/LC_MESSAGES/          # порожні msgstr: англійська — мова оригіналу
static/                      # статика проєкту
├── css/styles.css
├── js/book_search.js        # підказки пошуку в навбарі (fetch до /search/)
├── js/payment_status.js     # сторінка «оплата підтверджується»: опитує /orders/<pk>/status/
└── img/
    ├── no-cover.svg         # заглушка, коли обкладинки немає
    └── favicon.svg
media/                       # завантажені обкладинки (не в git)
logs/                        # app.log і його ротації (не в git)
requirements.txt             # залежності проєкту
requirements-dev.txt         # + django-debug-toolbar, пакети для тестів, black, flake8
tests/                       # див. «Тести»
pytest.ini                   # налаштування pytest, звіти покриття, мінімум 70%
.coveragerc                  # що рахується в покритті
pyproject.toml               # black: рядок 100, Python 3.13
.flake8                      # flake8: рядок 100, винятки, сумісні з black
.pre-commit-config.yaml      # pre-commit: black і flake8 на кожен git commit
nginx/default.conf           # nginx: /static/, /media/ з volumes, решта -> gunicorn (лише локально)
Dockerfile                   # образ: python:3.13-slim, користувач app, production-налаштування
.dockerignore                # що не потрапляє в образ (.env, .venv, бази, media)
gunicorn.conf.py             # порт з $PORT, воркери з WEB_CONCURRENCY, воркер uvicorn
docker-entrypoint.sh         # root на Railway -> chown media і далі як app; migrate + collectstatic (не для celery); exec команди
docker-compose.yml           # nginx + web + db + redis + celery + celery-beat + flower + stripe-cli
.gitattributes               # *.sh завжди з LF
```

## Користувачі та автентифікація

### Custom User Model

`users.User` наслідується від `AbstractUser`: усе вбудоване (username,
пароль, імена, `is_staff`, групи, права) лишається, змінено тільки email.

```python
# config/settings/base.py
AUTH_USER_MODEL = "users.User"
```

`AUTH_USER_MODEL` треба задати **до першого** `migrate`: таблиці адмінки, груп
і прав отримують зовнішній ключ саме на цю модель. Тому проєкт стартував з
нової бази (дані книжок перенесено через `dumpdata` / `loaddata`).

**Email:**
- обов'язковий і унікальний (`unique=True`, текст помилки в `error_messages`);
- завжди в нижньому регістрі: `User.clean()` (форми, адмінка) і `User.save()`
  (`createsuperuser`, `create_user()`, скрипти) переводять його в lowercase,
  тому `Ann@Mail.com` і `ann@mail.com` вважаються однією адресою;
- `CheckConstraint` `users_user_email_lowercase` гарантує це на рівні бази,
  навіть для `QuerySet.update()` і сирого SQL;
- міграція `0002_lowercase_email` спершу переводить наявні email у lowercase,
  а вже потім додає обмеження.

Вхід за **username** (як у вбудованого користувача).

### Вхід, вихід, реєстрація

| Сторінка | Як зроблено |
|---|---|
| Вхід | `LoginView` + `AuthenticationForm`; `redirect_authenticated_user = True`; повертає на `?next=...` |
| Вихід | `LogoutView`, **тільки POST** (Django 5+): у меню це кнопка всередині `<form>` з CSRF-токеном, а не посилання |
| Реєстрація | `CreateView` + `SignUpForm(UserCreationForm)`; після збереження `login()`, новий користувач потрапляє в групу Customers |

```python
LOGIN_URL = "users:login"            # куди Login/PermissionRequiredMixin відправляють гостей
LOGIN_REDIRECT_URL = "books:list"    # після входу, якщо немає ?next=
LOGOUT_REDIRECT_URL = "books:list"
```

`SignUpView` теж поважає `?next=`, але перевіряє адресу через
`url_has_allowed_host_and_scheme`, щоб не було переадресації на чужий сайт
(open redirect). Перевірку паролів (`AUTH_PASSWORD_VALIDATORS`), хешування і
перевірку username без урахування регістру робить сама `UserCreationForm`.

## Права доступу та групи

### Групи

Створюються data migration `users/0003_create_groups.py`:

| Група | Права (застосунок `books`) | Що може |
|---|---|---|
| **Customers** | `view_book`, `view_author`, `view_category` | лише переглядати; дається кожному новому користувачу |
| **Editors** | Customers + `add/change_book`, `add/change_author`, права на `bookcategory`; склад: `view_warehouse`, `view_stock` | додавати й редагувати книжки й авторів, бачити залишки |
| **Managers** | Editors + `delete_book`, `delete_author`, `add/change/delete_category`; склад: `view_warehouse`, `view_stock`, `add/change_stock` (`inventory.change_stock` — змінити кількість); замовлення: `view/change_order`, `view_orderitem`, `view_payment`, `add_payment` | усе в каталозі; замовлення в адмінці: статус, доставка, скасування, ручні платежі |

Суперкористувач має всі права без груп. Додати користувача в групу:
адмінка → Users → користувач → Groups.

Permissions зазвичай створює сигнал `post_migrate`, тобто **після** всіх
міграцій. На новій базі їх ще немає в момент `0003`, тому міграція спершу
викликає `create_permissions()` сама. Якщо в назві права помилка, міграція
падає з `RuntimeError`. Відкат (`migrate users 0002`) видаляє групи.

Права на видавництва (`books.Publisher`) — як на авторів, міграція
`users/0006_publisher_permissions.py`: Customers — `view_publisher`, Editors — ще
`add/change_publisher`, Managers — ще `delete_publisher`.

Права на замовлення додає окрема міграція `orders/0002_managers_order_permissions.py`
(тим самим способом). Вона робить `group.permissions.add()`, а не `set()`, тому
каталожні права групи лишаються; відкат прибирає лише ці 5 прав. Права на
видалення замовлень і на зміну чи видалення платежів не даються нікому:
замовлення скасовують, а платежі змінює лише `payments/services.py`.

### Перевірка прав

- **Views:** `PermissionRequiredMixin` стоїть першим у списку батьківських класів:
  ```python
  class BookCreateView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
      permission_required = "books.add_book"
  ```
  Гість отримує переадресацію на `LOGIN_URL?next=...`, а залогінений
  користувач без права отримує 403 (`templates/403.html`). Тому окремий
  `LoginRequiredMixin` тут не потрібен.
- **`LoginRequiredMixin`** стоїть на `ProfileView`: сторінка не вимагає
  конкретного права, достатньо бути залогіненим.
- **Шаблони:** `{% if perms.books.change_book %}` ховає кнопки Edit / Delete /
  Add book. Це лише зручність, справжній захист у views.

### Право `inventory.change_stock`

Кількість примірників змінює лише той, хто має `inventory.change_stock` (група
Managers), і лише в адмінці: на сторінці книги (`StockInline`, по складах) або в
списку «Залишки». У формі книги на сайті (`BookForm`) поля `stock` немає: нова
книжка отримує 0 примірників (`inventory.signals`), а надіслане в POST `stock`
форма ігнорує. Сторінка видалення книги, що є в замовленнях, веде менеджера
кнопкою «Редагувати в адмінці» туди, де залишок ставлять у 0. Детально — «Склад».

### Профіль

`/accounts/profile/` показує дані доставки (ім'я, телефон, адреса) з кнопкою «Edit»,
групи, статус (superuser / staff), коротке «що я можу» (✅/❌) і повний список
`user.get_all_permissions()`.

`/accounts/profile/edit/` (`ProfileEditView`): ім'я, прізвище, телефон, адреса.
`get_object()` повертає `request.user`, `<pk>` в адресі немає, тому чужий профіль
не відкриєш. Телефон перевіряє та сама `normalize_phone()`, що й при оформленні.

Суперкористувач бачить у профілі ще блок **«Інструменти»** (`users/tools.py`) —
усі службові сторінки в одному місці:

| Група | Посилання |
|---|---|
| Site | адмінка, замовлення, залишки на складі |
| API | browsable API `/api/`, Swagger, ReDoc, схема OpenAPI |
| Monitoring | `/health/`, Flower ↗, Sentry ↗ (якщо задано `SENTRY_ISSUES_URL`), тестова помилка `/sentry-debug/` |
| Payments | кабінет Stripe ↗ (тестовий або робочий — за ключем) |

Внутрішні адреси будуються через `reverse()`, зовнішні беруться з налаштувань;
не налаштований сервіс не показується. Іншим користувачам блок не видно:
Flower уміє зупиняти задачі, а `/sentry-debug/` — лише для суперкористувача.

## Django Debug Toolbar

Лише для розробки. Вмикається, коли виконуються всі три умови:

```python
ENABLE_DEBUG_TOOLBAR = (
    DEBUG and find_spec("debug_toolbar") is not None and not TESTING
)
```

- `DEBUG=True`: у продакшні тулбара немає взагалі (ні в `INSTALLED_APPS`, ні в URL);
- пакет встановлено (`requirements-dev.txt`): з одним `requirements.txt` проєкт працює;
- не тести: `TESTING = "test" in sys.argv or "pytest" in sys.modules`.

Тулбар бачать лише запити з `INTERNAL_IPS = ["127.0.0.1", "::1"]`, незалежно
від того, хто залогінений. Так можна дивитися SQL і шаблони очима гостя чи
звичайного покупця. `DebugToolbarMiddleware` стоїть одразу після `SecurityMiddleware`.

Тулбар зберігає дані в пам'яті (`MemoryStore`), тому його міграція прихована
і `migrate` її не показує, це нормально.

**У Docker тулбара немає:** образ ставить лише `requirements.txt`, і
`find_spec("debug_toolbar")` повертає `None`. Це навмисно: запити з Mac
приходять у контейнер з адреси шлюзу Docker (`192.168.65.1`), а не з
`127.0.0.1`, тож для тулбара довелося б розширювати `INTERNAL_IPS`. Для
налагодження з тулбаром запускайте `runserver` локально (див. «Встановлення та запуск»).

## Логування

`LOGGING` у `config/settings/base.py`: вивід у консоль і у файл `logs/app.log`
(`RotatingFileHandler`: 1 МБ, 5 архівних файлів, `utf-8`). Формат:

```
2026-11-07 21:02:39,943 INFO users.signals Login: user=ann ip=127.0.0.1
```

| Логер | Рівень | Що пише |
|---|---|---|
| `users` | DEBUG при `DEBUG=True`, інакше INFO | вхід, вихід, невдалий вхід (WARNING), реєстрація |
| `books` | так само | створення, зміна (`form.changed_data`), видалення книжок, хто це зробив |
| `orders` | DEBUG / INFO | листи (надіслано / помилка з traceback), `cancel_unpaid_orders` |
| `payments` | DEBUG / INFO | створення сторінки оплати, зміни статусів платежів, події webhook |
| `api` | DEBUG / INFO | видача JWT, створення / зміна (які поля) / видалення через API, замовлення й скасування, хто це зробив |
| `config` | INFO | рядок на кожен запит від `RequestTimingMiddleware` |
| `django` | WARNING | 404, 403 одним рядком; 500 з traceback |

- Події входу й виходу ловлять сигнали `user_logged_in`, `user_logged_out`,
  `user_login_failed` (`users/signals.py`): вони спрацьовують для будь-якого
  входу, зокрема в адмінці.
- У лог **не** пишуться паролі й email (персональні дані).
- `HideClientErrorTraceback` (`config/logging_filters.py`) прибирає traceback з
  записів про 4xx: для 403 це звичайна відмова, а не помилка. Фільтр стоїть на
  обробниках (handlers), бо фільтри логера `django` не діють на записи від
  дочірнього `django.request`.

```bash
tail -f logs/app.log             # локальний runserver
docker compose logs -f web       # у Docker: консольний вивід контейнера
```

У Docker `logs/app.log` пишеться всередині контейнера й зникає, коли контейнер
перестворюється (volume для логів немає). Основне джерело там — `docker compose logs`.
Access log gunicorn вимкнено: рядок на кожен запит уже пише `RequestTimingMiddleware`,
а `/health/` (Docker перевіряє його кожні 10 секунд) middleware не логує.

## Middleware: `RequestTimingMiddleware`

`config/middleware.py`, **перший** у `MIDDLEWARE`, тому вимірює роботу всіх
інших middleware, view і шаблону.

```
INFO config.middleware GET /?page=2&sort=price 200 23.6ms user=anonymous
INFO config.middleware GET /create/ 403 3.6ms user=ann
```

- **Лог:** метод, шлях із query string, статус, час, користувач. Запити довші
  за `REQUEST_SLOW_MS = 500` пишуться як WARNING. `/media/`, `/__debug__/` і `/health/` не логуються.
- **Заголовки:** `X-Request-Duration: 23.6ms` і стандартний
  `Server-Timing: app;dur=23.6` (видно в DevTools → Network → Timing).
- Час рахується через `time.perf_counter()` (монотонний годинник).
- `request.user` доступний, хоча middleware стоїть вище за
  `AuthenticationMiddleware`: та присвоює його тому самому об'єкту `request`
  ще до того, як відповідь повертається до нас.
- Працює і в синхронному режимі (`runserver`, WSGI), і в асинхронному
  (ASGI у Docker): див. «Асинхронні view та ASGI».

Реєстрація й вхід займають ~300 мс, решта сторінок кілька мілісекунд: це
хешування пароля (PBKDF2), воно навмисно повільне.

## Class-Based Views

| View | Шаблон за замовчуванням | Особливості |
|---|---|---|
| `BookListView` | `books/book_list.html` | `paginate_by = 10`; фільтри з GET-параметрів через `CatalogFilter`; `prefetch_related("categories")` |
| `BookDetailView` | `books/book_detail.html` | `prefetch_related("categories")` |
| `BookCreateView` | `books/book_form.html` | `PermissionRequiredMixin` (`add_book`); після збереження редирект на `get_absolute_url()` |
| `BookUpdateView` | `books/book_form.html` | `PermissionRequiredMixin` (`change_book`); той самий шаблон; заголовок і кнопки залежать від `object` |
| `BookDeleteView` | `books/book_confirm_delete.html` | `PermissionRequiredMixin` (`delete_book`); видалення тільки через POST; редирект на каталог |
| `AuthorListView` | `books/author_list.html` | `annotate(Count("books"))`, `paginate_by = 20` |
| `AuthorDetailView` | `books/author_detail.html` | книги автора через `author.books` |

Сторінки авторів тільки для перегляду: авторів додають і редагують в адмінці.
Посилання в адмінку видно, якщо користувач має `is_staff` **і** право
`add_author` / `change_author`.

Після створення, редагування й видалення `SuccessMessageMixin` показує
повідомлення (messages framework → Bootstrap alert), а `form_valid()`
пише запис у лог (див. «Логування»).

## Шаблони

- `base.html`: каркас сторінки з блоками `title` і `content`. Сторінки
  наслідуються від нього через `{% extends "base.html" %}`.
- `navbar.html`: прилипає до верху під час прокручування (`sticky-top`),
  підсвічує активний пункт меню (`request.resolver_match.url_name`), має
  швидкий пошук і на вузькому екрані згортається в «бургер». Праворуч:
  «🛒 Cart» з кількістю примірників (і для гостей), «Log in» / «Sign up» для гостей
  або меню користувача (email, «My profile», «My orders», «Log out»). «Add book» видно
  лише з правом `add_book`, «Admin» лише при `is_staff`.
- `pagination.html`: універсальна пагінація для будь-якого `ListView`.
  Тег `{% querystring page=N %}` зберігає поточні фільтри при переході між
  сторінками; довгий список сторінок скорочується (`get_elided_page_range`).
- `messages.html`: flash-повідомлення.

### Фільтри каталогу

`CatalogFilter` у `books/filters.py` (django-filter), метод GET (фільтри видно в
адресі, сторінку можна зберегти в закладки). Його основа `BookFilter` — ті самі
фільтри, що в API (`api/filters.py` лише підставляє свою форму), тож новий фільтр
додається один раз для сайту й API.

Кілька значень одного параметра — «або»: `?author=3&author=7` — книжки автора 3
або автора 7. Різні параметри — «і»: ці автори й водночас одна з вибраних категорій.

| Параметр | Що робить |
|---|---|
| `q` | пошук за назвою або іменем автора (без урахування регістру, зокрема для кирилиці) |
| `category` | категорія за `slug`; кілька: `?category=poetry&category=prose` |
| `author` | автор за `pk`; кілька: `?author=3&author=7` |
| `publisher` | видавництво за `pk`; кілька |
| `language` | мова: `uk`, `en`, `pl`, `de`, `fr`, `es`; кілька |
| `book_type` | тип: `paper`, `ebook`, `audiobook`; кілька |
| `cover_type` | обкладинка: `hard`, `soft`, `dust_jacket`; кілька |
| `year_min`, `year_max` | рік видання від–до; книга без року в жоден діапазон не потрапляє |
| `stock` | наявність: `in_stock` / `low` (≤ 5) / `out` |
| `price_min`, `price_max` | діапазон ціни; якщо «від» більше за «до», форма покаже помилку, а ціни не враховуються (так само рік) |
| `sort` | `title`, `-title`, `author__name`, `price`, `-price`, `-created_at`, `-sold` (спершу популярні) |
| `out_last` | `0` — вимкнути «Відсутні в кінці» (без параметра увімкнено) |

Некоректні значення (`?price_min=abc`, видалена категорія) не ламають сторінку:
форма показує помилку біля поля, а решта фільтрів працює (у `cleaned_data` після
`is_valid()` лишаються лише поля, що пройшли перевірку). Сортування завжди
закінчується `pk`: книжки з однаковою назвою чи ціною не «стрибають» між сторінками.

Категорії фільтруються підзапитом `EXISTS` (`BookFilter.filter_category`), а не JOIN
через `categories__in`: книжка з двох вибраних категорій інакше з'явилася б двічі, а
`.distinct()` погано поєднується з анотаціями й сортуванням списку. Видавництво, мова,
тип і обкладинка — поля самої книги, тож їм досить `IN (...)` (`BookFilter.filter_any_of`),
без власного `.distinct()` фільтра `MultipleChoiceFilter`.

**Лише наявні значення.** Блок пропонує тільки ті значення, що є хоча б в однієї книги
(`CatalogFilter.__init__`): з 32 видавництв міграції — лише ті, що мають книги, з 6 мов —
лише ті, якими є книги. Блок без жодного значення (`field|length`) не показується, блок
«Рік видання» — лише коли рік є хоча б в однієї книги. Старе посилання на видавництво,
яке вже без книг, показує помилку в панелі, як видалена категорія; API таке видавництво
приймає.

**Рік видання** — два поля й «Застосувати», як у ціни, але без повзунка
(`books/includes/year_filter.html`). Підказки в полях і межі для стрілок — найстаріше й
найновіше видання всього каталогу (`BookListView.year_range()`). Плашки:
«Рік: 2005–2020», «Рік: від 2015», «Рік: до 2015». Перевірку «від > до» для ціни й року
спільно робить `wrong_ranges()`: сайт діапазон пропускає з підказкою, API відповідає 400.

**Панель фільтрів** (`books/book_list.html`, `books/includes/filter_section.html`,
`static/js/filter_panel.js`): кожен фільтр — блок, що згортається (Bootstrap collapse;
згорнуті блоки браузер пам'ятає в `localStorage`). Блоки з галками й перемикачами
шаблон будує сам за полями `CatalogFilter` (`field.widget_type`), тож новий фільтр
у `books/filters.py` з'являється в панелі без змін шаблону.

- галка (автор, категорія) або перемикач (наявність) застосовує фільтр одразу;
  ціна чекає своєї кнопки «Застосувати»;
- текстового пошуку в панелі немає: це поле в шапці (`?q=`), панель передає його
  прихованим полем, тож галка пошук не скидає, а прибирає його плашка над списком;
- у довгому списку (понад 5 значень) видно перші 5 і всі вибрані, «Показати всі»
  відкриває решту; поле пошуку над списком ховає значення, що не підходять;
- порожні поля не відправляються (подія `formdata`), тож адреса без `?price_min=&price_max=`;
- без JavaScript видно всі значення, блоки відкриті, а форму відправляє кнопка
  «Застосувати» в `<noscript>`.

**На телефоні й планшеті** (вужче 992 px) панель схована й виїжджає зліва кнопкою
«Фільтри» над списком (Bootstrap `offcanvas-lg`: та сама розмітка на великому екрані —
колонка, на малому — бічна панель). На кнопці — кількість активних фільтрів, унизу
панелі — «Показати N книг», яка закриває її; число оновлюється після кожної зміни
(`data-sync`). Без JavaScript панель показана на місці, над списком. На великому
екрані панель прилипає під шапкою (`position: sticky` на обгортці offcanvas, бо
липкий елемент рухається лише в межах свого батька), прокручуються лише її поля.

**Без перезавантаження сторінки** (`static/js/catalog_live.js`): галка, «Застосувати»
ціни, плашки й «Очистити все», меню «Сортування», «На сторінці» й номери сторінок
не відкривають сторінку заново. Скрипт запитує ту саму адресу (той самий view і HTML,
окремого API немає) і з відповіді бере лише частину результатів
(`[data-catalog-results]`). Панель не замінюється, лише її поля отримують нові
значення, тож вона зберігає прокрутку, текст пошуку в списках, відкрите «Показати
всі» й згорнуті блоки. Адреса оновлюється через `history.pushState`: сторінку можна
зберегти в закладки, «Назад» і «Вперед» показують попередні списки. Новіший клік
скасовує запит попереднього (`AbortController`); якщо щось пішло не так (немає
мережі, помилка сервера), браузер просто відкриває адресу звичайним способом.

**Активні фільтри над списком:** кожне вибране значення — окрема плашка
(«Фріда Мак-Фадден ×», «Ціна: 100–500 ₴ ×»), хрестик прибирає лише його
(`CatalogFilter.chips()`: поточна адреса без цього значення й без номера сторінки).
«Очистити все» (`CatalogFilter.reset_url()`) прибирає всі фільтри, а сортування,
«На сторінці» й «Відсутні в кінці» лишаються. Неправильне значення плашки не має:
його помилка показана в панелі.

**Спершу популярні** (`?sort=-sold`): за кількістю проданих примірників, скасовані
замовлення не враховуються (`BookQuerySet.with_sold()`). Підзапит у тому самому
SELECT, як `with_stock()`, а не `Sum` через JOIN: разом із JOIN фільтра за
категорією він міг би порахувати рядки двічі. Підзапит додається лише для цього
сортування; книжки з однаковою кількістю (зокрема 0) йдуть за назвою.

**Відсутні в кінці** — галочка в меню «Сортування», увімкнена за замовчуванням:
книжки, яких немає в наявності, йдуть після всіх інших, а вибране сортування
працює всередині обох груп (`ORDER BY CASE WHEN stock = 0 THEN 1 ELSE 0 END, <сортування>, pk`;
`stock` уже є в запиті з `with_stock()`). Галочка — це посилання (`role="menuitemcheckbox"`),
тож працює без JavaScript; зняти її — `?out_last=0`, і «Застосувати» фільтрів це зберігає.

**Ціна повзунком.** Поля «від» і «до» стоять в одному рядку під підписом «Ціна, ₴»
(у валюті перемикача), під ними повзунок із двома ручками
(`books/includes/price_filter.html`, `static/js/price_range.js`):

- кінці повзунка — найдешевша й найдорожча книжка **всього** каталогу у вибраній
  валюті, цілими числами назовні (`BookListView.price_range()`: `MIN` і `MAX` того
  самого `price_in()`, що й фільтр, один SQL-запит). Межі не стискаються від
  фільтра, тож шкала не змінюється, поки користувач її тягне;
- повзунок не має `name` і лише заповнює поля, а відправляються саме поля. Ручка
  на своєму кінці очищає поле: «від найдешевшої» не додає `?price_min=` в URL;
- число, введене в поле, пересуває ручку; ручки не перетинаються;
- без JavaScript повзунок прихований (`hidden`), поля працюють як раніше; якщо всі
  книжки мають одну ціну або книжок немає, повзунка немає.

## Статичні файли і media

| | Static | Media |
|---|---|---|
| Що це | CSS, JS, іконки, заглушка обкладинки | обкладинки, завантажені через форму |
| Де лежить | `static/` (у git) | `media/covers/<рік>/<місяць>/` (не в git) |
| Налаштування | `STATIC_URL`, `STATICFILES_DIRS`, `STATIC_ROOT` | `MEDIA_URL`, `MEDIA_ROOT` |
| Хто роздає локально (`runserver`, `DEBUG=True`) | `runserver` сам | `serve_media` у `config/views.py` |
| Хто роздає в Docker (`DEBUG=False`) | nginx з volume `static_data` | nginx з volume `hillel_bookstore_media_data` |
| Хто роздає на Railway (nginx немає) | WhiteNoise (middleware) | `serve_media` з Volume, бо `DJANGO_SERVE_MEDIA=True` |

- У шаблонах статика підключається через `{% load static %}` і `{% static '...' %}`.
- `collectstatic` запускає `docker-entrypoint.sh` при кожному старті `web`.
- **Хеш в імені файлу** (production: `CompressedManifestStaticFilesStorage` від
  WhiteNoise): `collectstatic` записує кожен файл ще й з хешем вмісту в імені
  (`styles.css` → `styles.5a5d728b941a.css`) і стиснуті копії (`.gz`),
  а `{% static %}` дає ім'я з хешем. Змінений файл = нове ім'я, тому nginx
  і WhiteNoise дозволяють браузеру тримати статику рік (`immutable`), і після
  оновлення ніхто не бачить старий CSS. Тести працюють зі звичайним
  `StaticFilesStorage` (`config/settings/test.py`): без `collectstatic`.
- **WhiteNoise** стоїть одразу після `SecurityMiddleware` (спершу редирект на
  HTTPS, потім статика без решти middleware). Під ASGI він віддає файл у потоці;
  для кількох CSS і JS цього досить, а nginx локально лишається.
- **`serve_media`** (`config/views.py`) роздає лише `/media/`, лише при `DEBUG`
  або `SERVE_MEDIA`, лише GET і HEAD, з `Cache-Control` на 7 днів. Так зроблено
  для Railway: окремого сервера для файлів там немає, а обкладинок мало.
- Подробиці — у розділах «nginx» і «Деплой на Railway».

### Обкладинки книг

- Поле `Book.cover` (`ImageField`, необов'язкове).
- `Book.cover_url` повертає адресу обкладинки, а якщо її немає, то заглушки.
- Перевірки під час завантаження:
  - файл справді є зображенням (Pillow);
  - формат JPG, PNG або WebP (SVG і GIF заборонені);
  - розмір до 2 МБ.
- На сторінці редагування видно прев'ю поточної обкладинки й чекбокс
  «Remove cover» (власний віджет `CoverInput` на основі `ClearableFileInput`).
- Форма відправляється з `enctype="multipart/form-data"`, без нього файл не дійшов би на сервер.

## Моделі

| Модель | Поля | Примітки |
|---|---|---|
| `Category` | `name`, `slug` | обидва унікальні |
| `Author` | `name`, `bio` | `name` унікальне; `bio` необов'язкове |
| `Publisher` | `name` | унікальне; основні українські видавництва створює data migration `books/0012_create_publishers.py` (32 назви), нові додають в адмінці |
| `Book` | `title`, `author`, `description`, `publisher`, `language`, `publication_year`, `cover`, `categories`, `created_at`, `updated_at` | спільне для всіх форматів; `author` — ForeignKey на `Author` з `on_delete=PROTECT` (не можна видалити автора, у якого є книги); зв'язок ManyToMany з категоріями через `BookCategory`; характеристики — див. нижче; `get_absolute_url()`, `cover_url`, `active_formats`, `main_format`, `stock`, `available` |
| `BookFormat` | `book`, `format_type`, `price`, `currency`, `cover_type`, `pages`, `is_active` | те, що продається: паперова / електронна / аудіокнига; див. «Формати книг» |
| `BookCategory` | `book`, `category` | проміжна модель; `on_delete=PROTECT` не дає видалити категорію, у якій є книги; пара `book + category` унікальна |

**Характеристики видання** (`books/0011_publisher_book_details.py`). Усі необов'язкові,
тож книги, додані раніше, лишилися правильними:

| Поле | Значення | Перевірка |
|---|---|---|
| `publisher` | ForeignKey на `Publisher`, `null` — невідоме | `PROTECT`: видавництво з книгами не видаляється |
| `language` | `uk` / `en` / `pl` / `de` / `fr` / `es` (коди ISO 639-1), `""` — невідома | — |
| `publication_year` | рік | від 1450 до поточного року |

Значення вибору — `TextChoices` (`Book.Language.UKRAINIAN`): у базі й в адресі
фільтра — код (`?language=uk`), на сайті — перекладений підпис
(`get_language_display()` → «Українська»). Верхню межу року перевіряє функція
`validate_not_future_year`, а не `MaxValueValidator(2026)`: число записалося б у
міграцію назавжди й з 2027 року не пропускало б нові книги. Тип, обкладинка й
сторінки — у форматів.

`BookQuerySet.by_stock_status()` фільтрує книги за наявністю. Його
використовують і каталог, і адмінка; поріг «мало» задає `LOW_STOCK_THRESHOLD = 5`.

| Модель | Поля | Примітки |
|---|---|---|
| `User` | + `phone`, `address` | необов'язкові; підставляються у форму оформлення |
| `Order` | `user`, `status`, `payment_status`, `full_name`, `phone`, `address`, `currency`, `exchange_rate`, `total`, `created_at`, `updated_at` | `user` з `PROTECT`; дані доставки — копія, а не посилання на профіль; `total ≥ 0` (`CheckConstraint`) |
| `OrderItem` | `order`, `book`, `format`, `format_type`, `title`, `price`, `original_price`, `original_currency`, `exchange_rate`, `quantity` | `order` з `CASCADE`, `book` і `format` з `PROTECT`; `title`, `format_type` і `price` — копії на момент замовлення; один рядок на формат (`UniqueConstraint`), `quantity ≥ 1`; `cost` = `price × quantity`; `display_title` — «Тигролови (Паперова)» |
| `Payment` | `order`, `provider`, `external_id`, `amount`, `currency`, `status`, `details` (JSON), `created_at`, `updated_at`, `paid_at` | `order` з `PROTECT`; `provider`: `stripe` / `manual`; `status`: `pending` / `succeeded` / `failed` / `expired`; `(provider, external_id)` унікальні для непорожнього `external_id`; `amount > 0` |

Два незалежні статуси замовлення:
- `status` — що з товаром: `new` → `processing` → `shipped` → `completed`, або `cancelled`;
- `payment_status` — скільки сплачено: `unpaid` / `partially_paid` / `paid`. Зберігається
  в базі (для фільтра в адмінці), але змінює його лише `Order.refresh_payment_status()`
  із суми успішних платежів. Відсоток оплати (`paid_percent`) не зберігається, а рахується.

### Перенесення авторів в окрему модель

Раніше автор був текстовим полем `Book.author`. Перенесення зроблено
чотирма міграціями, щоб не втратити дані:

| Міграція | Що робить |
|---|---|
| `0003_rename_author_book_author_name` | перейменовує текстове поле на `author_name` |
| `0004_author_book_author` | створює `Author` і тимчасовий необов'язковий `Book.author` |
| `0005_move_authors_to_author_model` | data migration: для кожного імені створює `Author` (`get_or_create`) і пов'язує з книгами |
| `0006_remove_book_author_name_alter_book_author` | видаляє `author_name`, робить `author` обов'язковим |

Просто замінити `CharField` на `ForeignKey` під тим самим іменем не можна:
Django згенерував би `AlterField` і спробував би перетворити імена авторів на числові id.
Усі чотири міграції можна відкотити (`python manage.py migrate books 0002`).

## Формати книг

Одна книга (назва, автор, опис, видавництво, мова, рік, категорії, обкладинка-картинка)
продається в кількох форматах, кожен зі своєю ціною:

```
«Тигролови»   paper      450 UAH, тверда обкладинка, 320 сторінок, 7 на складі
              ebook      199 UAH
              audiobook    5 USD
```

```
BookFormat: book → Book (CASCADE), format_type (paper / ebook / audiobook),
            price ≥ 0, currency → Currency (PROTECT, типово UAH),
            cover_type (лише paper), pages (не для audiobook), is_active («У продажу»)
            unique (book, format_type)
```

- **Правила.** Один формат кожного типу на книгу (`UniqueConstraint`). Обкладинка лише
  в паперового, сторінок немає в аудіокниги (`BookFormat.clean()`; та сама перевірка у
  формі, адмінці й API). Формат, що вже є в замовленнях, не видаляють, а знімають з
  продажу (`is_active = False`): старі замовлення його зберігають.
- **Каталог.** Картка показує ціну «від» — найдешевший формат у продажу у валюті
  перемикача (`Book.objects.with_display_price()`, один підзапит на книгу). За цим
  числом працюють фільтр і сортування за ціною та повзунок. Книга з кількома форматами
  має кнопку «Обрати формат» (на сторінку книги), з одним — «У кошик».
- **Сторінка книги.** Плитки форматів у продажу з ціною (`btn-check`, `name="format"`);
  «У кошик» додає вибраний. У «Характеристиках» — формати, обкладинка паперового,
  сторінки.
- **Форма книги на сайті.** Під полями книги — рядки форматів (`BookFormatFormSet`:
  щонайменше один, щонайбільше три). Книга й формати перевіряються разом і
  зберігаються однією транзакцією (`BookFormatsMixin`); формат із замовлень не можна
  видалити, лише зняти з продажу.
- **Наявність.** Склад є лише в паперового формату (див. «Склад»); файл завжди
  доступний. Книга «в наявності» (`Book.objects.with_availability()`, анотація
  `available`), якщо в продажу є цифровий формат або паперовий з примірниками.
  Нею користуються кнопка картки, «Відсутні в кінці», фільтр наявності («Мало» —
  лише папір), пошук і `in_stock` в API.
- **Кошик і замовлення** — за форматом (див. «Кошик», «Замовлення»).
- **Фільтри.** `?book_type=ebook` — книги, які можна купити як електронні (формати в
  продажу); `?cover_type=hard` — обкладинка паперового формату. Параметр не
  `?format=`, бо DRF резервує його для формату відповіді (`?format=json`).
- **API** — окремий ресурс `/api/formats/` (див. «REST API»).

**Міграції** (усі можна відкотити):

| Міграція | Що робить |
|---|---|
| `books 0013`, `0014` | таблиця `BookFormat`; кожна наявна книга отримує один формат зі своїх полів (тип, ціна, валюта, обкладинка, сторінки) |
| `users 0007` | права на формати: Customers — перегляд; Editors і Managers — усі |
| `inventory 0004`–`0006` | `Stock.book` → `Stock.format` (рядки паперового формату; рядки електронних видаляються) |
| `orders 0008`–`0010` | `OrderItem.format` + `format_type`; старі рядки отримують формат своєї книги; унікальність (замовлення, формат) |
| `books 0015`–`0017` | старі поля книги (`price`, `currency`, `book_type`, `cover_type`, `pages`) видаляються; назад — заповнюються з головного формату |

`books 0015` залежить від `orders 0009`: та читає старі поля книги, тож на базі, що
отримує всі міграції одним запуском (Railway), поля видаляються лише після неї.

## Адмінка

- **Книги:**
  - колонки: мініатюра обкладинки, автор, формати з цінами (знятий з продажу
    закреслено), ціна «від» у гривнях (із сортуванням), залишок, ознака наявності, категорії;
  - автор вибирається з пошуком під час введення (`autocomplete_fields`);
  - inline з форматами (ціна, валюта, обкладинка, сторінки, «У продажу»); посилання
    рядка відкриває сторінку формату, де в паперового — залишок за складами;
  - фільтри: наявність (є / мало ≤ 5 / немає), категорії, формат, мова, видавництво, дата;
  - пошук за назвою, іменем автора, описом, категорією й видавництвом;
  - `date_hierarchy`, `fieldsets` із секціями «Details» (характеристики, кілька полів у
    рядку) і «Cover» (прев'ю обкладинки), inline для категорій;
  - видавництво, як і автор, вибирається з пошуком (`autocomplete_fields`).
- **Формати книг:** окремий список (тип, ціна, валюта, «У продажу», залишок), фільтри
  за типом, продажем і валютою.
- **Автори:** кількість книг (із сортуванням), пошук за іменем, біографія.
- **Видавництва:** кількість книг (із сортуванням), пошук за назвою.
- **Категорії:** кількість книг (із сортуванням), автозаповнення `slug`,
  inline зі списком книг.
- **Замовлення** (`orders/admin.py`):
  - колонки: номер, користувач, статус, статус оплати, сплачений відсоток (підзапит
    у тому самому SQL), сума, дата; фільтри: статус, оплата, дата; пошук за номером,
    email, username, ім'ям, телефоном;
  - inline: книги замовлення й усі платежі (лише перегляд) і рядки «add a manual payment»;
  - ручний платіж зберігається через `record_manual_payment()` (блокування, перевірка
    залишку, перерахунок статусу), а не через `formset.save()`;
  - статус `cancelled` у формі або дія «Cancel selected orders» викликають
    `cancel_order()`: книги повертаються на склад. Скасоване замовлення не відновлюється;
  - додавати й видаляти замовлення не можна; зберігаються лише змінені поля
    (`update_fields`), щоб не перезаписати оплату, що прийшла, поки сторінка була відкрита.
- **Платежі:** окремий список лише для перегляду (фільтри за провайдером і статусом).
- **Користувачі:** розділ «Delivery details» (телефон, адреса).
- Запити оптимізовано через `select_related` / `prefetch_related` та `annotate`.

## Валюти

Ціни, кошик, замовлення й оплата працюють у кількох валютах (типово UAH, USD,
EUR). Застосунок `currencies/`, курси — Національного банку України.

```
НБУ ──(Celery Beat, update_exchange_rates)──► ExchangeRate (історія курсів)
                                                   │
                       current_rates() у кеші ◄────┘
                                │
   перемикач у навбарі ─► ціни, каталог, кошик у вибраній валюті
                                │
   оформлення ─► Order.currency + курс дня ─► Stripe у валюті замовлення
```

### Моделі

| Модель | Поля | Примітки |
|---|---|---|
| `Currency` | `code` (первинний ключ, `"USD"`), `name`, `symbol`, `is_active` | код за ISO 4217; UAH, USD, EUR створює міграція `0002_create_currencies` |
| `ExchangeRate` | `currency`, `date`, `rate`, `source` (`nbu` / `manual`), `created_at`, `updated_at` | **уся історія**: рядок на валюту й день (`UniqueConstraint`); `rate > 0`; рядків для UAH немає |
| `BookFormat` | + `currency` | валюта ціни формату, `ForeignKey` з `PROTECT`, типово UAH |
| `Order` | + `currency`, `exchange_rate` | валюта замовлення й курс у день замовлення (гривень за 1 одиницю) |
| `OrderItem` | + `original_price`, `original_currency`, `exchange_rate` | ціна формату в його валюті на момент замовлення й крос-курс, яким її перераховано |
| `Payment` | + `currency` | завжди валюта замовлення |

- **Курс — «скільки гривень за 1 одиницю»**, як у НБУ. Будь-яке перерахування йде
  через гривню, крос-курси не зберігаються:
  ```
  650 UAH -> USD:  650 × 1 / 45.4274        = 14.3085… -> 14.31
  20 USD  -> EUR:  20 × 45.4274 / 50.3379   = 18.0489… -> 18.05
  ```
- **Округлення один раз**, у кінці, до копійки (`ROUND_HALF_UP`): проміжні курси не
  округлюються, інакше результат міг би відрізнятися на копійку.
- **Спочатку ціна одного примірника, потім кількість**: 3 × 14.31 = 42.93, а не
  1950 / 45.4274 = 42.93…: кошик, замовлення й лист показують ті самі числа.
- **«Сьогодні» — дата в Києві** (`Europe/Kyiv`), а не в UTC: НБУ встановлює курс на
  київський день.

### Курси НБУ

`currencies/nbu.py` читає `https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json&date=YYYYMMDD`
(без ключа, без реєстрації; числа читаються одразу як `Decimal`, без `float`).

- **Задача `update_exchange_rates`** (Celery Beat, о 6:05 і щогодини з 13:05 до 17:05 UTC):
  НБУ публікує курс **наступного** дня близько 15:30 за Києвом, кілька запусків
  підхоплять його, навіть якщо НБУ запізниться. Повторний запуск перезаписує ті самі
  числа (`update_or_create`), нічого не дублюється.
- **Сьогодні й найновіший день**: задача завантажує курс на сьогодні і, якщо є,
  на завтра. Лише «найновіший» після 15:30 дав би тільки завтрашній курс, і до
  півночі сайт не мав би курсу на сьогодні.
- **Ручний курс не перезаписується**: менеджер може внести курс в адмінці
  (`source = manual`), наприклад, якщо НБУ помилився.
- **НБУ недоступний** (`NBUError`, мережа): нічого не змінюється, сайт працює з
  останнім відомим курсом; мережеві помилки задача повторює ще 3 рази.
- **Кеш**: `current_rates()` — найновіший курс кожної валюти не пізніше сьогодні,
  одним запитом (`DISTINCT ON`), у кеші до кінця дня. Будь-яке збереження курсу чи
  валюти очищає кеш після COMMIT (`currencies/signals.py`).

```bash
python manage.py update_exchange_rates                    # сьогодні + найновіший день
python manage.py update_exchange_rates --date 2026-11-13  # один день (заповнити пропуск)
```

### Курси НБУ з підтвердженням (сторінка для адміністраторів)

`/currencies/rates/` (`NBURatesView`), посилання «Отримати курси НБУ» у профілі. Доступ —
у кого є права `currencies.add_exchangerate` і `currencies.change_exchangerate`
(суперкористувач або група з обома правами): анонім іде на вхід, інші отримують 403.

1. **GET** запитує НБУ (найновіші курси або день із поля «День», `?date=2026-11-16`) і
   показує таблицю: число НБУ, курс, уже збережений на цей день (з джерелом), і поле з
   числом НБУ. Нічого не зберігається.
2. Поле можна виправити: значок поруч одразу показує, як його буде збережено
   («НБУ» чи «Вручну», `static/js/rates_confirm.js`). Порожнє поле — валюту не зберігати.
3. **POST** «Підтвердити й зберегти» (`services.save_confirmed_rates`, одна транзакція):
   - число дорівнює числу НБУ (як числа: `45.427400 == 45.4274`) → `source = nbu`,
     навіть поверх ручного курсу: людина бачила обидва й вибрала число НБУ;
   - змінене число або курс, якого в НБУ немає → `source = manual`, і автоматичне
     оновлення його не перезапише.

   Потім редірект на ту саму сторінку з цим днем (Post/Redirect/Get) і повідомлення
   «Курси на 17.11.2026 збережено: EUR (Вручну), USD (НБУ).»

Відповідь НБУ їде у формі прихованим полем, підписаним `SECRET_KEY` (`django.core.signing`,
`currencies/forms.py`): POST знає, які саме числа бачила людина, без другого запиту до
НБУ (той за хвилину може відповісти інакше), а змінене число в прихованому полі ламає
підпис. Сторінка, відкрита понад годину, завантажується заново. Якщо НБУ не відповідає
або ще не має курсів на вибраний день, сторінка про це каже, а таблиці немає.

### Перемикач і ціни на сайті

- **Перемикач у навбарі** (`POST /currency/`) зберігає код у сесії, як і кошик:
  працює для гостей і лишається після входу. Пропонуються лише активні валюти з
  курсом (`available_currencies()`), гривня перша.
- **Ціна формату** — шаблонний тег `{% book_price book_format %}`: «14,31 $»
  українською, «$14.31» англійською; ціна «від» книги — `{% price_from book %}`. На
  сторінці книги під перерахованою ціною — «650,00 ₴ за курсом НБУ на 16.11.2026».
- **Сортування й фільтр за ціною** рахує база: `price_in("USD")` будує
  `CASE WHEN currency_id = 'UAH' THEN ROUND(price * 0.0220…, 2) … END` з курсами як
  константами (без JOIN до таблиці курсів), для кожного формату; ціна «від» — найменше
  з них. Сортується й фільтрується саме те число, яке видно на сторінці; книги без
  курсу чи без формату в продажу (`NULL`) — в кінці.
- **Кошик** показує ціни й суму у валюті перемикача.

### Замовлення у валюті

```
сторінка оформлення: сума у валюті перемикача + прихована валюта у формі
  POST -> create_order(..., currency="USD"):
    1. валюта пропонується (активна, з курсом)?  інакше помилка, нічого не збережено
    2. ОДНЕ читання курсів на все замовлення
    3. кожен формат: price = convert(format.price, format.currency, "USD")
       + original_price, original_currency, exchange_rate (крос-курс)
    4. Order.currency = "USD", Order.exchange_rate = 45.4274 (гривень за 1 $)
```

- **Валюта обирається лише під час оформлення** і потім не змінюється: сума
  замовлення, оплати й борг — у ній.
- **Прихована валюта у формі**, а не з сесії під час POST: перемикач, змінений в
  іншій вкладці, не створить замовлення в сумі, якої покупець не бачив. На сторінці
  оформлення є свій перемикач валюти.
- **Курси замовлення зберігаються**: замовлення не змінюється, коли змінюються курси.
- **Звіти в гривнях**: щоденний звіт додає замовлення різних валют за курсом дня
  кожного замовлення (`Order.total_uah = total × exchange_rate`); у CSV є колонки
  `currency` і `total_uah`.

### Оплата у валюті

- Stripe Checkout отримує валюту платежу (`"usd"`, `"eur"`, `"uah"`) і суму в
  мінімальних одиницях: 62.93 $ → `6293`. Валюти без копійок (JPY) чи з трьома
  знаками (KWD) Stripe рахує інакше, тому для них онлайн-оплата недоступна.
- **Webhook і сторінка повернення перевіряють суму й валюту**, які взяв Stripe
  (`session_matches()`): якщо вони не ті, що в платежі, оплата не зараховується,
  помилка йде в лог і Sentry, а Stripe отримує 200 (без повторів) — рішення за менеджером.
- Ручна оплата менеджера — у валюті замовлення; листи, сторінки й адмінка
  показують суми з символом валюти.

### Адмінка

- **Currencies**: список з поточним курсом; вимкнена валюта (`is_active`) зникає з
  перемикача, але старі формати й замовлення в ній лишаються.
- **Exchange rates**: історія, фільтр за валютою й джерелом; курс, внесений вручну,
  завжди `manual`.
- Формат: поле валюти поруч із ціною; замовлення: валюта, курс, початкова ціна
  кожної позиції.

## Кошик

`cart/cart.py`, клас `Cart`. Кошик живе в сесії, тому працює й для гостей:

```python
# ключ — id формату: та сама книга паперова й електронна — два рядки
request.session["cart_formats"] = {"15": {"quantity": 2}, "16": {"quantity": 1}}
```

- Ключі — рядки: сесія зберігається як JSON, а в JSON ключі завжди рядки.
- Зберігається лише кількість. Ціна щоразу береться з бази й перераховується у
  валюту перемикача (`cart.currency`): кошик показує поточну ціну, і змінити її
  через сесію неможливо.
- `add(book_format, quantity=1, override=False)`: кнопка «Add to cart» додає до
  наявного, поле на сторінці кошика (`override=True`) задає точну кількість. Кількість
  паперового обмежена залишком; електронна й аудіокнига — без обмеження.
- `POST /cart/add/<book_id>/` читає вибраний `format` (формат іншої книги — 404, без
  формату — головний формат книги, `Book.main_format`).
- **Зміна формату в кошику**: список у рядку (`POST /cart/change_format/<format_id>/`,
  `change_format()`), кількість переходить на новий формат; якщо він уже є в кошику —
  кількості додаються.
- `remove(book_format)`, `clear()`; `for item in cart` → `format`, `book`, `quantity`,
  `price`, `cost`, `exceeds_stock`, `not_on_sale`, `format_choices`. Усі формати одним
  запитом з книгами й залишком, результат кешується, тож `cart.total` другого запиту
  не робить. Видалені з бази формати тихо зникають з кошика.
- Старий кошик за книгами (ключ `cart`) один раз переводиться на головні формати.
- `len(cart)` — кількість примірників, читає лише сесію, без SQL: лічильник у навбарі
  є на кожній сторінці (context processor `cart.context_processors.cart`).
- Зміна вкладеного словника не позначає сесію зміненою, тому `_save()` щоразу
  присвоює `session["cart"]` і ставить `session.modified = True`.
- При вході Django зберігає дані сесії (змінюється лише її id), тож кошик гостя
  лишається після входу. Вихід очищає сесію разом із кошиком.
- Усі зміни — лише POST (`require_POST`); після дії повертає на `next`, перевірений
  через `url_has_allowed_host_and_scheme` (без переадресації на чужий сайт).

## Замовлення

### Оформлення: `orders.services.create_order()`

```
POST /orders/checkout/  (форма: full_name, phone, address + прихована currency)
  transaction.atomic():
    1. SELECT ... FOR UPDATE рядків складу паперових форматів, ORDER BY format_id
    2. кожен формат у продажу, паперовий — з достатнім залишком
       -> проблема? OrderError -> ROLLBACK, усі проблеми разом
    3. Order + OrderItem (bulk_create), назви, тип формату й ціни копіюються з бази,
       ціни перераховуються у валюту замовлення (див. «Валюти»)
    4. резерв паперових: stock -= quantity (bulk_update); файлам резерв не потрібен
    5. on_commit(лист «order created»)
  COMMIT -> кошик очищається -> сторінка замовлення з кнопкою «Pay»
```

- **`transaction.atomic()`:** замовлення, позиції й зміни складу зберігаються разом
  або не зберігаються взагалі. Немає замовлення без позицій і не списаних «у нікуди» книг.
- **`select_for_update()`:** без блокування двоє покупців могли б одночасно прочитати
  `stock = 1` і обидва купити останній примірник. З блокуванням другий чекає COMMIT
  першого й бачить `stock = 0`. Перевірено двома потоками: одне замовлення, друге
  отримує «out of stock».
- **`ORDER BY format_id`:** усі транзакції блокують рядки в однаковому порядку, тому не
  чекають одна одну по колу (deadlock).
- **Резерв** при оформленні, а не при оплаті: поки покупець платить, книги ніхто не забере.
- **Лист після COMMIT** (`transaction.on_commit`): після ROLLBACK лист не піде.
- Форма містить лише дані доставки; `user`, `total` і статуси ставить сервіс, тож
  підроблений POST із `total=1` нічого не дасть. Телефон `+380 (67) 123-45-67`
  зберігається як `+380671234567` (`users/phone.py`).
- Поля підставляються з профілю (`first_name` + `last_name`, `phone`, `address`);
  галочка «Save phone and address to my profile» оновлює профіль для наступного разу.

### Скасування: `orders.services.cancel_order()`

- Блокує замовлення, перевіряє правила вже під блокуванням, повертає паперові книги
  (`UPDATE ... SET stock = stock + n` через `F()`), ставить `cancelled`.
- Покупець може скасувати лише своє замовлення в статусі `new` і `unpaid`
  (`can_be_cancelled_by_customer`); менеджер — будь-яке не скасоване.
- Після COMMIT відкрита сторінка оплати Stripe закривається (`close_open_payments`),
  щоб за скасоване замовлення не можна було заплатити.
- Чуже замовлення дає 404 (як і неіснуюче), а не 403: так не видно, що замовлення з таким номером є.

### My orders

`/orders/` (меню користувача): власні замовлення від нових до старих, кількість книг
(`annotate(Sum("items__quantity"))`), сума, бейджі статусів. З `annotate` Django
ігнорує `Meta.ordering`, тому сортування задано явно: `order_by("-created_at", "-pk")`.

## Оплата

### Провайдери

`payments/providers/`: решта проєкту не імпортує Stripe напряму, а працює з контрактом
`PaymentProvider` (`start()`, `fetch_status()`, `cancel()`, `handle_webhook()`).
Новий провайдер — новий клас і рядок у `registry.py`.

| Провайдер | Як платять | Хто створює `Payment` |
|---|---|---|
| `stripe` | картка на сторінці Stripe Checkout | кнопка «Pay» |
| `manual` | готівка, переказ тощо | менеджер в адмінці; сума може бути частиною (→ `partially_paid`) |

Усі зміни платежів (`payments/services.py`) — у транзакції, спочатку блокується
замовлення (те саме блокування, що в `cancel_order()`), в кінці
`refresh_payment_status()`. Два менеджери, що одночасно вносять по 120 ₴ на замовлення
в 200 ₴, не перевищать суму: другий отримає «до сплати лише 80,00 ₴».

### Stripe Checkout

```
«Pay» -> start_online_payment():
   transaction (lock order): своє? не скасоване? є що сплачувати?
       відкрита сторінка на ту саму суму ще жива?  -> її URL (без нової)
       інакше Payment(pending, amount = amount_due)
   після транзакції: Stripe API -> Checkout Session (валюта замовлення, копійки чи центи, 31 хв)
       помилка Stripe -> Payment = failed, замовлення лишається
-> checkout.stripe.com -> покупець платить
-> /payments/success/?session_id=cs_test_...  -> статус питаємо в Stripe -> succeeded
-> Stripe -> stripe-cli -> POST /payments/webhook/stripe/ -> те саме, якщо ще не зроблено
```

- Одна позиція «Bookstore: order #N» на суму `amount_due`: після часткової ручної
  оплати списується лише залишок. Валюта — валюта замовлення; UAH, USD, EUR мають
  два знаки після коми, тому сума в копійках чи центах (`250.50` → `25050`).
- Оплата зараховується, лише якщо Stripe взяв саме цю суму в цій валюті
  (див. «Валюти» → «Оплата у валюті»).
- Запит до Stripe — **після** транзакції: мережевий виклик не тримає замовлення
  заблокованим, а відкотити його однаково неможливо.
- Ключ ідемпотентності (`bookstore-payment-<id>-<час>`): повтор після мережевої
  помилки не створить другу сесію.
- Подвійний клік чи «назад» зі Stripe і знову «Pay» дають ту саму сторінку; застаріла
  (інша сума, менше 5 хв до кінця) закривається через `sessions.expire`.
- `session_id` в адресі повернення — не доказ оплати (її може набрати будь-хто): за
  ним лише знаходимо платіж, а статус беремо в Stripe секретним ключем.
- Сторінка повернення й webhook ведуть до тих самих ідемпотентних функцій: хто
  перший, той зараховує оплату, другий нічого не змінює (і другого листа немає).

### Webhook

`/payments/webhook/stripe/`, `csrf_exempt` (запит іде від Stripe, не з нашої форми).
Справжність перевіряє `stripe.Webhook.construct_event()`: HMAC-SHA256 сирого тіла
(`request.body`) із `STRIPE_WEBHOOK_SECRET` і час не старший 5 хвилин.

| Подія | Що робимо |
|---|---|
| `checkout.session.completed` + `payment_status = paid` | платіж `succeeded`, якщо сума й валюта ті самі, що в платежі |
| `checkout.session.completed` + `unpaid` | чекаємо (банківські списання приходять пізніше) |
| `checkout.session.async_payment_succeeded` / `_failed` | `succeeded` / `failed` |
| `checkout.session.expired` | `expired` (лише з `pending`; замовлення не скасовується) |

- 400 — лише без підпису, з чужим підписом чи зламаним JSON. На інші події й чужі
  сесії відповідь 200: на будь-яку не-2xx Stripe повторює запит кілька днів.
- Повтор тієї самої події нічого не змінює; запізніле `expired` не скасує оплату.

**Stripe CLI** (сервіс `stripe-cli` у compose): Stripe не може достукатися до
`localhost:8000` з інтернету, тому CLI тримає вихідне з'єднання зі Stripe і пересилає
4 потрібні події на `web:8000/payments/webhook/stripe/` з правильним підписом.
`web` має `web` в `ALLOWED_HOSTS` (compose додає до `DJANGO_ALLOWED_HOSTS`). Лише для
розробки: у продакшні Stripe викликає публічний HTTPS-endpoint із Dashboard → Webhooks.

```bash
docker compose logs -f stripe-cli    # <-- [200] POST http://web:8000/payments/webhook/stripe/
```

### Акаунт Stripe

- Тестовий режим (`sk_test_...`): реальних грошей немає. Картка `4242 4242 4242 4242`,
  будь-яка майбутня дата й CVC.
- Україна не входить до країн, де Stripe-акаунт можна активувати, тому акаунт
  зареєстровано з підтримуваною країною й ніколи не активовано: лише тестові ключі.
- UAH, USD і EUR Stripe підтримує як валюти платежу. Мінімальна сума — еквівалент
  0.50 у валюті виплат акаунта (близько 0,50 $ чи 25 ₴).
- Publishable key не потрібен: сторінка оплати на боці Stripe, Stripe.js на сайті немає.

## Email

Поштовик вибирається за змінними, перший налаштований (`config/settings/base.py`):

| Що задано | Поштовик | Де |
|---|---|---|
| `BREVO_API_KEY` (+ `EMAIL_FROM`) | **Brevo HTTP API** через `django-anymail` | Railway: SMTP там заблокований, HTTPS — ні |
| `EMAIL_HOST_USER` + `EMAIL_HOST_PASSWORD` | Gmail SMTP | локально |
| нічого | консоль: лист друкується в лог | локально без пошти |

### Brevo (Railway)

Railway на тарифах Free / Trial / Hobby блокує вихідний SMTP (порти 25, 465,
587). Brevo приймає лист JSON-запитом на `https://api.brevo.com/v3/smtp/email`,
а HTTPS Railway пропускає. `django-anymail` — поштовик Django, який перетворює
звичайний `EmailMessage` (текст, HTML, вкладення CSV звіту) на такий запит, тож
код листів не змінився:

```python
MAILERS = {
    "default": {
        "BACKEND": "anymail.backends.brevo.EmailBackend",
        "OPTIONS": {"api_key": BREVO_API_KEY},  # Django 6.1 передає OPTIONS у поштовик
    },
}
```

- **API-ключ:** Brevo → SMTP & API → API Keys → Generate (`xkeysib-...`).
- **Відправник** має бути підтверджений у Brevo (Senders, Domains & Dedicated IPs →
  Senders → Add a sender, лист із кодом на цю адресу): `EMAIL_FROM`. Без
  `EMAIL_FROM` production не стартує (`ImproperlyConfigured`): інакше Brevo
  відхиляв би кожен лист.
- Помилки API (`AnymailRequestsAPIError`) — це `requests.HTTPError`, тобто
  `OSError`: задачі Celery повторюють їх так само, як помилки SMTP.
- Тест (`tests/unit/test_settings.py`) відправляє лист з production-налаштуваннями,
  підмінивши HTTP-запит, і перевіряє адресу API, ключ, відправника й отримувача.

### Gmail SMTP (локально)

`MAILERS` з Django 6.1 (старі `EMAIL_BACKEND`, `EMAIL_HOST`, ... застарілі й зникнуть у 7.0):

```python
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {"host": "smtp.gmail.com", "port": 587, "use_tls": True,
                    "username": EMAIL_USER, "password": EMAIL_PASSWORD, "timeout": 10},
    },
}
```

- Пароль — **App Password** Google (16 літер; потрібна двоетапна перевірка), не пароль
  акаунта. Пробіли з нього прибираються. Ліміт Gmail — близько 500 листів на добу.
- Без `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` листи друкуються в консоль
  (`docker compose logs web`). Тести самі підміняють усі mailers на `locmem`.
- `DEFAULT_FROM_EMAIL = "Bookstore <EMAIL_FROM або адреса Gmail>"`: Gmail відправляє
  лише від імені акаунта, під яким входить, Brevo — лише від підтвердженого відправника.
- Посилання в листах будуються від `SITE_URL`: лист відправляється без запиту
  (після COMMIT, з webhook), `request.build_absolute_uri()` там недоступний.

Листи пишуться **мовою отримувача** (`User.language`): див. «Інтернаціоналізація».

| Лист | Коли |
|---|---|
| «order created» | після COMMIT оформлення: позиції, сума, доставка, посилання |
| «payment received» | Stripe: кожен успішний платіж; ручний: коли замовлення сплачене повністю |

- Кожен лист має текстову й HTML-версії (`EmailMultiAlternatives`); HTML зі стилями
  в атрибутах `style`, бо Gmail і Outlook ігнорують `<style>`.
- Відправка ніколи не кидає виняток: помилку SMTP (пароль, мережа, таймаут) записує
  лог з traceback, а замовлення вже збережене.
- Відправка — у задачах Celery після COMMIT (див. «Celery»).
- Перевірити пошту: `docker compose exec web python manage.py sendtestemail адреса@gmail.com`;
  на Railway — `railway ssh --service web -- python manage.py sendtestemail адреса@gmail.com`.
- Тестові користувачі: адреси з `+` (`адреса+ann@gmail.com`) приходять у ту саму
  скриньку, а для сайту це різні email.

## Інтернаціоналізація (i18n)

Мови: українська (`uk`, за замовчуванням) і англійська (`en`). Перекладається
інтерфейс; дані (книги, автори) — ні, див. «Відомі обмеження».

```python
# config/settings/base.py
LANGUAGE_CODE = "uk"
LANGUAGES = [("uk", _("Ukrainian")), ("en", _("English"))]
LOCALE_PATHS = [BASE_DIR / "locale"]
MIDDLEWARE = [..., "django.contrib.sessions.middleware.SessionMiddleware",
              "django.middleware.locale.LocaleMiddleware", ...]
```

### Як визначається мова

`LocaleMiddleware` на кожному запиті бере мову в такому порядку:

1. cookie `django_language` (ставить перемикач мови);
2. заголовок браузера `Accept-Language`;
3. `LANGUAGE_CODE` = `uk`.

URL без префікса мови (`/en/...` немає): адреси однакові для обох мов.

**Перемикач у навбарі** (🌐) — форма `POST /i18n/setlang/` (`config/views.py`, `set_language`):

- ставить cookie на рік і повертає на ту саму сторінку;
- для залогіненого зберігає вибір у `User.language`;
- при вході (`UserLoginView`) мова з профілю стає мовою сайту, тож вибір
  переходить на інший пристрій;
- при реєстрації в профіль записується мова, якою людина реєструвалась;
- невідомий код (`de`) ігнорується: вбудований view Django перевіряє лише, що
  в Django є переклади для коду, а не `settings.LANGUAGES`.

### Що позначено для перекладу

| Де | Як |
|---|---|
| моделі | `verbose_name`, `help_text`, `choices` через `gettext_lazy` (`_`) |
| форми, адмінка, `apps.py` | `gettext_lazy` |
| views, сервіси (повідомлення) | `gettext` під час запиту; `ngettext` для чисел |
| шаблони | `{% translate %}`, `{% blocktranslate %}` (зі змінними, `count`, `trimmed`) |
| листи | шаблони листів + `translation.override(user.language)` |

- `gettext_lazy` — у коді, що виконується при імпорті (поля моделей, форм):
  мова ще невідома, переклад береться пізніше, при показі. `gettext` — усередині
  функцій, коли запит уже має мову.
- Змінні в текстах — іменовані: `_("“%(title)s” is out of stock.") % {"title": ...}`.
  Перекладач бачить, що підставиться, і може змінити порядок слів.
- **Множина.** Українська має 4 форми (`Plural-Forms: nplurals=4`):
  «1 книга, 3 книги, 5 книг, 21 книга». Фільтр `|pluralize` знає лише англійську,
  тому `{% blocktranslate count counter=... %}` і `ngettext`.
- Текст у JavaScript (`confirm(...)` скасування замовлення) — через
  `{% blocktranslate asvar %}` + `|escapejs`, щоб апостроф не зламав JS.
- Числа й суми форматуються за мовою: `14,31 $` / `$14.31` (`currencies.display.format_money`).
- Права (`Can change stock quantity`) і логи лишаються англійською: це технічні
  рядки, у лог пишеться `order #5`, а не перекладене «Замовлення #5».

### Листи мовою отримувача

```python
# orders/emails.py
def send_order_email(order, template_prefix, extra_context=None):
    with translation.override(order.user.language):
        return _send(order, template_prefix, extra_context)
```

Лист рендериться мовою з профілю клієнта, а не мовою запиту: webhook від
Stripe приходить без cookie, менеджер з англійською адмінкою додає оплату
україномовному клієнтові — лист однаково правильною мовою.

### Файли перекладів

```bash
python manage.py makemessages -l uk -l en --ignore=.venv   # зібрати тексти в .po
# перекласти msgstr у locale/uk/LC_MESSAGES/django.po
python manage.py compilemessages --ignore=.venv            # .po -> .mo
```

- Потрібен GNU gettext (`brew install gettext`).
- `.mo` **у git**: у Docker-образі gettext немає, а Django читає саме `.mo`.
  Після зміни `.po` обов'язково `compilemessages`, інакше сайт показуватиме старий
  текст (це ловить тест `test_compiled_mo_matches_the_po`).
- `locale/en/` з порожніми `msgstr`: англійська — мова оригіналу в коді.

## Асинхронні view та ASGI

### Три async view

| View | Асинхронні запити | Хто викликає |
|---|---|---|
| `health` (`config/views.py`) | `ContentType.objects.aexists()`, `cache.aset` / `aget` / `adelete`, `asyncio.gather` | healthcheck Docker |
| `order_status` (`orders/views.py`) | `await request.auser()`, `.annotate(paid=Sum(..., filter=Q(...))).values(...).afirst()`: замовлення і сума платежів одним запитом | `static/js/payment_status.js` кожні 2 с |
| `book_search` (`books/views.py`) | `async for book in queryset` (з `select_related`) | `static/js/book_search.js` під час набору |

```python
@never_cache
@require_GET
async def order_status(request, pk):
    user = await request.auser()          # request.user зробив би синхронний запит
    if not user.is_authenticated:
        return JsonResponse({"error": "login required"}, status=401)
    order = await (Order.objects.filter(pk=pk, user=user)
                   .annotate(paid=Sum("payments__amount",
                                      filter=Q(payments__status=Payment.Status.SUCCEEDED)))
                   .values("pk", "status", "payment_status", "total", "paid").afirst())
    ...
```

- У async view не можна викликати синхронний ORM: Django кине
  `SynchronousOnlyOperation`. Тому `request.auser()` замість `request.user`,
  `afirst()`, `async for`.
- **Сторінка «Оплата підтверджується».** Клієнт часто повертається зі Stripe
  раніше, ніж приходить webhook. Сторінка опитує `/orders/<pk>/status/` і, щойно
  `payment_status` змінився, сама відкриває замовлення (максимум ~1 хвилина).
- **Підказки пошуку.** Запит через 250 мс після останньої клавіші, від 2 літер;
  старий запит скасовується (`AbortController`), назви вставляються через
  `textContent` (не `innerHTML`), тож `<script>` у назві лишиться текстом.
- JSON віддає і коди (`"paid"`) для логіки, і підписи мовою запиту
  (`"Оплачено"` / `"Paid"`), і суми у форматі мови (`"250,50"` / `"250.50"`).

### ASGI у Docker

```
gunicorn (керує процесами, перезапускає впалі)
  └─ 3 воркери DjangoUvicornWorker (uvicorn: event loop, протокол ASGI)
       └─ config.asgi:application → middleware → view
```

```dockerfile
CMD ["gunicorn", "config.asgi:application"]
```

Решту налаштувань gunicorn читає сам із `gunicorn.conf.py` (з коментарем до кожного):

| Налаштування | Значення | Навіщо |
|---|---|---|
| `bind` | `0.0.0.0:$PORT`, типово 8000 | Railway сам вибирає порт і передає його в `PORT` |
| `workers` | `WEB_CONCURRENCY`, типово 3 | на малому тарифі менше пам'яті: на Railway `WEB_CONCURRENCY=2` |
| `worker_class` | `config.uvicorn_worker.DjangoUvicornWorker` | uvicorn з `lifespan: off`: Django не підтримує подію lifespan і відповідав на неї `ValueError`, який Sentry записував при кожному старті |
| `forwarded_allow_ips` | `*` | довіряти `X-Forwarded-*` від проксі (nginx, Railway) |
| `control_socket_disable` | `True` | з версії 25.1 gunicorn відкриває сокет у `$HOME`, а в користувача `app` домашньої папки немає |

- **Async view** виконуються прямо в event loop; поки view чекає на базу, воркер
  обслуговує інші запити. **Звичайні (sync) view** працюють як і раніше: Django
  запускає їх у потоці.
- **Middleware для обох режимів.** Якщо хоч один middleware лише синхронний,
  Django під ASGI запускає його й усе нижче в потоці на кожен запит, і
  асинхронність втрачається. Тому `RequestTimingMiddleware` має `__call__` і
  `__acall__` (`sync_capable = async_capable = True`). Статику під ASGI Django
  сам не роздає: локально її віддає nginx, на Railway — WhiteNoise.
- **Пул з'єднань** замість `CONN_MAX_AGE`:
  ```python
  "CONN_MAX_AGE": 0,
  "OPTIONS": {"pool": {"min_size": 2, "max_size": 10, "timeout": 10}},
  ```
  Під ASGI запити до бази йдуть з різних потоків; постійні з'єднання тримались
  би окремо на кожен потік і накопичувались. Пул (`psycopg-pool`) ділить кілька
  з'єднань між усіма потоками процесу.
- Перевірено навантаженням: 300 паралельних `/health/` і 200 `/search/` —
  усі 200.

## Тести

```bash
pip install -r requirements-dev.txt
docker compose up -d db               # тестова база test_bookstore створюється в цьому PostgreSQL
pytest                                # усі тести + покриття (термінал і htmlcov/index.html)
pytest tests/unit                     # лише unit
pytest tests/api --no-cov             # лише REST API
pytest -k webhook --no-cov            # кілька тестів за назвою, без покриття (швидше)
open htmlcov/index.html               # непокриті рядки підсвічені
```

| | Кількість | Що перевіряють |
|---|---|---|
| `tests/unit/` | 453 | одна функція, модель, форма або один запит; склад, валюти й курси, задачі Celery, Sentry, налаштування production, gunicorn, версія у футері |
| `tests/integration/` | 86 | сценарії з кількох кроків: кошик → замовлення → Stripe → webhook → лист; оплата у валюті; кеш |
| `tests/api/` | 125 | REST API через `APIClient`: токени, права кожної ролі, фільтри, валюти, замовлення, CORS, throttling, кеш |
| `tests/test_setup.py` | 7 | сама інфраструктура: налаштування, фабрики, фейки |

Покриття **98.89%** (786 тестів); `--cov-fail-under=70` у `pytest.ini`: якщо покриття впаде
нижче 70%, `pytest` завершиться з помилкою. Ті самі тести запускає CI на кожен push
і pull request, а звіт `htmlcov` лежить в артефактах запуску (див. «CI/CD»).

### Структура

```
tests/
├── conftest.py            # фікстури: користувачі й клієнти, fake_stripe, failing_mailer, ізольований MEDIA_ROOT
├── factories.py           # factory-boy: User, Category, Author, Book, Order (+ items), OrderItem, Payment
├── fakes.py               # FakeStripeClient, підписані події webhook (із сумою й валютою сесії)
├── helpers.py             # message_levels(), дані форм адмінки
├── unit/
│   ├── test_models.py             # моделі на 100%; кожен тест позначено «Generated with AI, reviewed and modified»
│   ├── test_forms.py, test_cart_and_helpers.py, test_views.py
│   ├── test_language.py           # перемикач мови, User.language
│   ├── test_async_views.py        # async view через AsyncClient
│   ├── test_payment_services.py   # відмови й помилки оплат
│   ├── test_inventory.py          # Warehouse / Stock, with_stock(), права складу
│   ├── test_currencies.py         # курси: моделі, НБУ (фейкова відповідь), перерахування, кеш, команда, задача, сторінка «Курси НБУ»
│   ├── test_book_currency.py      # валюта книги: форма, адмінка, price_in(), seed_books
│   ├── test_book_details.py       # характеристики: модель, міграції, адмінка, форма, сторінка, фільтри, плашки
│   ├── test_display_currency.py   # перемикач, формат сум, каталог і кошик у валюті
│   ├── test_order_currency.py     # замовлення у валюті: перерахування, курси, оформлення, звіти, адмінка
│   ├── test_tasks.py              # задачі Celery: повтори листів, розклад, звіт, скасування
│   ├── test_sentry.py             # що йде в Sentry (через справжній ASGI-застосунок)
│   ├── test_deploy.py             # підроблений X-Forwarded-For, сторінка 500
│   └── test_translation_catalog.py  # .po повний, .mo скомпільований
├── api/
│   ├── conftest.py                # api_client, get_tokens(user), as_user(user), editor
│   ├── test_setup.py              # JWT, ліміт /api/token/, документація, CORS
│   ├── test_cache.py              # кеш авторів і категорій, нове покоління після змін
│   ├── test_catalog.py            # книги, автори, категорії: права, фільтри, 409, мова помилок
│   ├── test_book_details.py       # характеристики в API, їхні фільтри, /api/publishers/
│   ├── test_currencies.py         # /api/currencies/, ?currency=, display_price, валюта замовлення
│   └── test_orders.py             # свої / чужі замовлення, створення, скасування, 405, Idempotency-Key (і гонка двох потоків)
└── integration/
    ├── test_checkout_flow.py      # зокрема гонка: два покупці за останній примірник
    ├── test_payment_flow.py       # Stripe: сторінка, повернення, webhook, один лист
    ├── test_payment_currency.py   # оплата у валюті замовлення, перевірка суми й валюти
    ├── test_admin_and_commands.py # адмінка менеджера, management-команди
    ├── test_book_management.py    # менеджер і редактор: права на книги
    ├── test_cache.py              # кеш книги й фрагментів, очищення сигналами, логи
    ├── test_language_flow.py, test_translations.py  # сайт і листи двома мовами
    └── test_async_flow.py         # опитування статусу до і після webhook
```

### Фікстури й моки

- **factory-boy** (`tests/factories.py`): `BookFactory(title="Kobzar", categories=[poetry])`,
  `OrderFactory(user=ann, items=[(book, 2)])` — сума рахується з позицій.
- **Stripe** — `FakeStripeClient` замість `StripeProvider._client` (фікстура
  `fake_stripe`): запам'ятовує створені сесії, вміє «оплатити» (`pay()`),
  «прострочити» (`expire_session()`) і впасти (`fail_with`). Webhook-запити
  підписуються справжнім HMAC, тому перевірка підпису теж тестується.
- **Email** — `mailoutbox` (pytest-django, бекенд `locmem`): листи нікуди не
  йдуть. Листи після COMMIT — через `django_capture_on_commit_callbacks(execute=True)`.
  `failing_mailer` імітує падіння SMTP: замовлення має зберегтися.
- **Налаштування тестів** (`config/settings/test.py`): MD5-хеш паролів (швидко),
  `LocMemCache` замість Redis, фейкові ключі Stripe, без пулу з'єднань і без запису в `logs/app.log`,
  `CELERY_TASK_ALWAYS_EAGER=True` (задача виконується одразу, разом з повторними спробами, без брокера),
  Sentry не запускається.

### Async-тести

```python
pytestmark = [
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
    pytest.mark.usefixtures("async_db_connections"),
]

async def test_order_status_needs_login(order_of_ann):
    response = await AsyncClient().get(reverse("orders:status", args=[order_of_ann.pk]))
    assert response.status_code == 401
```

- `AsyncClient` проводить запит через ASGI-обробник, як у Docker.
- `transaction=True`: асинхронний ORM працює в іншому потоці з іншим з'єднанням
  і не бачить даних з незакоміченої транзакції звичайного тесту.
- `serialized_rollback=True`: після очищення таблиць Django повертає дані з
  міграцій (групи, права), інакше наступні тести їх не знайдуть.
- Фабрики в async-тестах — через `await sync_to_async(BookFactory)(...)`.
- `async_db_connections` закриває з'єднання потоку `sync_to_async` після тесту;
  без цього pytest не може видалити `test_bookstore` наприкінці.
- Тестова база створюється заново на кожен запуск (без `--reuse-db`): тест гонки
  з `transaction=True` очищає таблиці, і повторно використана база стартувала б без груп.

## Встановлення та запуск

### У Docker

```bash
cp .env.example .env
# згенерувати SECRET_KEY і вставити в .env В ОДИНАРНИХ ЛАПКАХ (див. нижче):
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# заповнити POSTGRES_PASSWORD, EMAIL_HOST_USER / EMAIL_HOST_PASSWORD (Gmail), STRIPE_SECRET_KEY

# спільні volume створюються один раз (див. «Спільні volume»)
docker volume create hillel_bookstore_postgres_data && docker volume create hillel_bookstore_media_data

docker compose run --rm --no-deps stripe-cli listen --print-secret   # whsec_... -> STRIPE_WEBHOOK_SECRET у .env
docker compose up --build -d                                   # зібрати образ і запустити
docker compose ps                                              # db, redis, web, nginx, celery, flower healthy
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_books            # якщо база порожня
```

- Сайт: http://localhost:8000/ (nginx → gunicorn)
- Адмінка: http://localhost:8000/admin/
- API: http://localhost:8000/api/, документація: http://localhost:8000/api/docs/
- Стан: http://localhost:8000/health/
- Flower: http://localhost:5555/ (логін і пароль з `FLOWER_BASIC_AUTH`)
- Логи: `docker compose logs -f web celery`, запити: `docker compose logs -f nginx`,
  події Stripe: `docker compose logs -f stripe-cli`

```
docker compose up
  ├─ db           postgres:17-alpine  ──┐ healthcheck: pg_isready
  ├─ redis        redis:8-alpine      ──┤ healthcheck: redis-cli ping
  │                                     ▼ обидва healthy
  ├─ web          docker-entrypoint.sh → migrate → collectstatic → exec gunicorn (uvicorn workers)
  │                                     healthcheck: GET /health/
  │                                     ▼ healthy (міграції застосовано, статика зібрана)
  ├─ nginx        :8000 → /static/, /media/ з volumes; решта → web:8000
  ├─ celery       celery worker (2 процеси): листи, звіт, скасування
  │                                     ▼ healthy (celery inspect ping)
  ├─ flower       :5555 → панель задач
  ├─ celery-beat  celery beat: кладе періодичні задачі в чергу за розкладом
  └─ stripe-cli   stripe listen --forward-to nginx/payments/webhook/stripe/ (після nginx healthy)
```

| Сервіс | Порт на Mac | Volume | Healthcheck |
|---|---|---|---|
| `db` | 5432 | `hillel_bookstore_postgres_data` (спільний) → `/var/lib/postgresql/data` | `pg_isready` |
| `redis` | 6379 | немає (кеш можна втратити, сесії є і в PostgreSQL) | `redis-cli ping` |
| `web` | немає, лише в мережі Docker (`expose: 8000`) | `static_data` → `/app/staticfiles`, `hillel_bookstore_media_data` (спільний) → `/app/media` | `GET /health/` (Python `urllib`, у slim-образі немає curl) |
| `nginx` | 8000 → 80 | ті самі `static_data` і media, лише читання (`:ro`) | `wget /health/` крізь nginx до Django |
| `celery` | немає | немає | `celery inspect ping` |
| `celery-beat` | немає | немає (файл розкладу в `/tmp`) | немає |
| `flower` | `127.0.0.1:5555` (лише цей Mac) | немає | `GET /healthcheck` |
| `stripe-cli` | немає | немає | немає: від нього ніхто не залежить, стан видно в `logs` |

`web`, `celery`, `celery-beat` і `flower` — один образ `hillel-bookstore-django`
з однаковими налаштуваннями (якір `x-django` у `docker-compose.yml`), різні лише команди.

Корисні команди:

```bash
docker compose logs -f web                         # вивід Django / gunicorn
docker compose logs -f celery celery-beat          # задачі: received / succeeded / retry; розклад
docker compose logs -f nginx                       # кожен запит (access log) і помилки nginx
docker compose exec web python manage.py shell     # команда в запущеному контейнері
docker compose restart web                         # перезапуск (entrypoint знову зробить migrate)
docker compose down                                # зупинити й видалити контейнери, volumes лишаються
docker compose down -v                             # ... і видалити static_data (спільні база й обкладинки лишаються)
docker compose exec web python manage.py cancel_unpaid_orders --dry-run
```

**Що варто знати:**

- `docker-entrypoint.sh` має `set -e`: якщо `migrate` впаде, gunicorn не стартує.
  Для `celery ...` (worker, beat, flower) він пропускає `migrate` і `collectstatic`:
  їх робить лише `web`, решта чекає, поки `web` стане healthy.
  `exec "$@"` робить gunicorn процесом PID 1, тому він отримує `SIGTERM` від
  `docker compose stop` і завершується коректно.
- Контейнер працює від користувача `app` (не root). Писати він може лише в
  `staticfiles/`, `media/`, `logs/`. Файли, скопійовані через `docker compose cp`,
  належать root: `docker compose exec -u root web chown -R app:app /app/media`.
- `.env` не потрапляє в образ (`.dockerignore`), compose передає змінні через
  `env_file`. Хости в `.env` — `localhost` (для локального запуску);
  `docker-compose.yml` перевизначає їх: `POSTGRES_HOST=db`,
  `REDIS_URL=redis://redis:6379` (сервіси бачать один одного за іменем;
  кеш бере базу 0, черга Celery — базу 1), `DJANGO_HTTPS=False` (локально
  немає сертифіката) і `SENTRY_ENVIRONMENT=docker`. `DEBUG` у Docker вимкнено
  завжди: образ працює з `config.settings.production`.
- **`$` у значеннях `.env`.** Docker compose сприймає `$abc` як змінну й підставляє
  порожній рядок (`WARN The "abc" variable is not set`). Ключ від
  `get_random_secret_key()` може містити `$`, тому його беремо в **одинарні**
  лапки: `DJANGO_SECRET_KEY='...'`. Подвійні лапки не допомагають.
- Налаштування gunicorn — у `gunicorn.conf.py` (див. «ASGI у Docker»).

### Спільні volume

База й обкладинки лежать у volume з фіксованими іменами, однакових для всіх наступних ДЗ:

```yaml
volumes:
  postgres_data:
    name: hillel_bookstore_postgres_data
    external: true
  media_data:
    name: hillel_bookstore_media_data
    external: true
```

- `name:` — ім'я volume як є. Без нього compose додає префікс проєкту (назву папки),
  і кожна нова папка ДЗ отримувала б нові порожні volume.
- `external: true` — compose не створює й не видаляє ці volume: `down -v` спільну
  базу не зітре. Якщо volume немає, `up` зупиниться з `external volume not found`;
  тоді `docker volume create ...` (команда в «У Docker»).
- `static_data` лишається окремим для проєкту: `collectstatic` заповнює його при кожному старті.
- Одночасно запустити два ДЗ не вийде: обидва займають порти 5432, 6379 і 8000.
- `.env` однаковий в усіх ДЗ: пароль PostgreSQL записаний у самій базі при першому старті.

Перенесення з volume ДЗ №18 (один раз, контейнери hw_18 зупинені):

```bash
docker run --rm -v hillel_hw_18_django_postgres_docker_postgres_data:/from -v hillel_bookstore_postgres_data:/to alpine cp -a /from/. /to/
docker run --rm -v hillel_hw_18_django_postgres_docker_media_data:/from -v hillel_bookstore_media_data:/to alpine cp -a /from/. /to/
```

`cp -a` зберігає власників файлів (`postgres` для бази, `app` для обкладинок).

### Локально (runserver + PostgreSQL і Redis з Docker)

Для розробки з Debug Toolbar. PostgreSQL і Redis беруться з контейнерів через
опубліковані порти (`POSTGRES_HOST=localhost`, `REDIS_URL=redis://localhost:6379/0` у `.env`).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # або requirements.txt без Debug Toolbar і тестів

docker compose up -d db redis         # тільки база й Redis
python manage.py migrate
python manage.py runserver
```

- Сайт: http://127.0.0.1:8000/ (саме `127.0.0.1`, щоб з'явився Debug Toolbar)
- `runserver` працює через WSGI: async view теж працюють (Django запускає їм
  event loop на кожен запит), але без переваг ASGI. Як у Docker:
  `uvicorn config.asgi:application --reload` (без Debug Toolbar).
- Лог: `logs/app.log`
- Якщо контейнер `web` теж запущений, він уже займає порт 8000:
  `docker compose stop web` або `runserver 8001`.

### Перенесення даних із SQLite у PostgreSQL

Так дані з ДЗ №16 (`db.sqlite3`, `media/`) переїхали в Docker:

```bash
# 1. Поки settings.py ще на SQLite (до перемикання на PostgreSQL):
DJANGO_DEBUG=False python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --exclude admin.logentry --exclude sessions --indent 2 -o data.json

# 2. У запущений контейнер web (migrate вже створив таблиці й групи):
docker compose cp data.json web:/tmp/data.json
docker compose exec web python manage.py loaddata /tmp/data.json
docker compose exec -u root web rm /tmp/data.json

# 3. Обкладинки у volume media_data:
docker compose cp media/. web:/app/media/
docker compose exec -u root web chown -R app:app /app/media
```

- `DJANGO_DEBUG=False`: щоб у дамп не потрапив `debug_toolbar` (змінна з
  командного рядка важливіша за `.env`, `load_dotenv()` її не перезаписує).
- `--natural-foreign`: зв'язки за природними ключами, а не за `id`: група як
  `["Editors"]`, permission як `["change_stock", "inventory", "stock"]`. `id` permissions
  у PostgreSQL інші, тому інакше не можна.
- `--natural-primary`: у `User` і `Group` немає `pk`. Групи вже створила
  міграція `users.0003`, `loaddata` знаходить їх за назвою й оновлює, а не дублює.
- `contenttypes`, `auth.permission` створює `migrate`; лог адмінки й сесії не переносимо.
- Книги, автори, категорії переносяться зі своїми `id` (адреси `/15/` не змінюються).
  `loaddata` на PostgreSQL сам скидає sequences: нова книга отримує наступний `id`.
- `data.json` містить хеші паролів і email, тому він у `.gitignore` і `.dockerignore`.
- Перевірка: кількість записів кожної моделі збігається з дампом
  (`bookcategory 18`, `book 12`, `author 10`, `category 5`, `group 3`, `user 3`).

### Змінні оточення (`.env`)

| Змінна | Опис | Приклад |
|---|---|---|
| `DJANGO_SECRET_KEY` | секретний ключ (обов'язковий), в одинарних лапках | `'change-me'` |
| `DJANGO_DEBUG` | режим налагодження, лише для `development` (runserver); production його ігнорує | `True` |
| `DJANGO_ALLOWED_HOSTS` | хости через кому (`localhost` потрібен і для healthcheck); на Railway домен додається сам | `127.0.0.1,localhost` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | production: додаткові адреси для перевірки CSRF (через кому) | `https://shop.example.com` |
| `DJANGO_HTTPS` | production: редирект на HTTPS, secure cookies, HSTS; compose ставить `False` | `True` |
| `DJANGO_HSTS_SECONDS` | production: скільки браузер пам'ятає «лише HTTPS» | `3600` |
| `DJANGO_SERVE_MEDIA` | production: Django сам роздає `/media/` (Railway, де немає nginx) | `False` |
| `DATABASE_URL` | база однією адресою (Railway, CI); якщо задана — `POSTGRES_*` не потрібні | `postgresql://user:pass@host:5432/db` |
| `POSTGRES_DB` | назва бази (обов'язкова); контейнер `db` створює її при першому старті | `bookstore` |
| `POSTGRES_USER` | користувач бази (обов'язковий) | `bookstore` |
| `POSTGRES_PASSWORD` | пароль (обов'язковий) | |
| `POSTGRES_HOST` | `localhost` для runserver; у Docker compose ставить `db` | `localhost` |
| `POSTGRES_PORT` | порт | `5432` |
| `REDIS_URL` | сервер Redis: кеш і сесії в базі 0, черга Celery в базі 1; у Docker compose — `redis://redis:6379` | `redis://localhost:6379` |
| `CELERY_BROKER_URL` | лише щоб винести чергу на інший сервер; порожня — `REDIS_URL`, база 1 | |
| `FLOWER_BASIC_AUTH` | логін і пароль Flower `user:password`, без коми; **обов'язкова** для `docker compose` | `'admin:change-me'` |
| `FLOWER_URL` | адреса Flower для посилання в профілі | `http://localhost:5555` |
| `SENTRY_DSN` | адреса проєкту Sentry; порожня — Sentry вимкнено | `https://...@o....ingest.sentry.io/...` |
| `SENTRY_ENVIRONMENT` | середовище в Sentry; у Docker compose ставить `docker` | `local` |
| `SENTRY_TRACES_SAMPLE_RATE` | частка запитів із таймінгами (Performance) | `0.1` |
| `SENTRY_ISSUES_URL` | сторінка Issues проєкту для посилання в профілі; порожня — без посилання | |
| `EMAIL_HOST_USER` | адреса Gmail; порожня → листи в консоль | `name@gmail.com` |
| `EMAIL_HOST_PASSWORD` | App Password Google (16 літер), не пароль акаунта | |
| `BREVO_API_KEY` | ключ API Brevo; якщо заданий — листи йдуть через Brevo, а не Gmail | `xkeysib-...` |
| `EMAIL_FROM` | адреса відправника, підтверджена в Brevo; без неї — логін Gmail | `shop@example.com` |
| `SITE_URL` | адреса сайту для посилань у листах і `site_url` в API | `http://localhost:8000` |
| `CORS_ALLOWED_ORIGINS` | домени фронтендів, яким браузер дозволить читати `/api/` (через кому); порожньо — нікому | `http://localhost:3000` |
| `STRIPE_SECRET_KEY` | секретний ключ Stripe, тестовий режим | `sk_test_...` |
| `STRIPE_WEBHOOK_SECRET` | підпис webhook; друкує `stripe-cli listen --print-secret` | `whsec_...` |

`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` читають і Django, і образ
`postgres`, тому один `.env` обслуговує обидва. Змінювати їх після першого старту
`db` марно: база вже створена у volume.

## Налаштування

Пакет `config/settings/`: спільна частина і по файлу на кожне середовище.
Кожен файл починається з `from .base import *` і змінює лише своє.

| Файл | Де працює | Хто його вибирає | Що змінює |
|---|---|---|---|
| `base.py` | — (лише основа) | — | усе спільне: застосунки, база, кеш, Celery, LOGGING, Sentry; `DEBUG=False` |
| `development.py` | `runserver`, команди `manage.py` на Mac | типове значення в `manage.py` | `DEBUG` (можна вимкнути `DJANGO_DEBUG=False`), Debug Toolbar, логи DEBUG |
| `production.py` | Docker (локально й на Railway) | `ENV DJANGO_SETTINGS_MODULE` у `Dockerfile`; типове в `asgi.py`, `wsgi.py`, `celery.py` | без `DEBUG`, HTTPS, WhiteNoise, хости Railway |
| `test.py` | `pytest` | `pytest.ini` | швидкий хеш паролів, кеш у пам'яті, фейкові ключі Stripe |

**Production** (`config/settings/production.py`):

- `DEBUG = False` без жодної змінної, яка могла б його ввімкнути.
- Без `DJANGO_ALLOWED_HOSTS` сервер не стартує (`ImproperlyConfigured`), а не
  відповідає 400 на кожен запит. На Railway домен сервісу (`RAILWAY_PUBLIC_DOMAIN`)
  і хост його перевірки здоров'я (`healthcheck.railway.app`) додаються самі.
- **HTTPS** (`DJANGO_HTTPS`, типово `True`): редирект з `http://` (крім `/health/`:
  Railway перевіряє його звичайним HTTP), cookies сесії, CSRF і мови лише через
  HTTPS, HSTS на годину (`DJANGO_HSTS_SECONDS`). `SECURE_PROXY_SSL_HEADER`:
  HTTPS закінчується на проксі Railway, а Django дізнається про нього з
  `X-Forwarded-Proto`. Локальний `docker compose` ставить `DJANGO_HTTPS=False`:
  сертифіката на `localhost` немає.
- Перевірка: `python manage.py check --deploy` без жодного попередження
  (`tests/unit/test_settings.py` запускає її з production-налаштуваннями).

**Змінні з однієї адреси** (`config/env.py`):

- `DATABASE_URL=postgresql://user:password@host:5432/name` (так базу дають
  Railway і CI); без неї — `POSTGRES_*` з `.env`, як раніше.
- `REDIS_URL=redis://host:6379` — один сервер: кеш і сесії в базі 0, черга Celery
  в базі 1 (`redis_url()` дописує номер). Railway дає одну адресу без номера бази.

## CI/CD

`.github/workflows/django.yml` запускається на кожен push у `main`, на кожен
pull request і вручну (`workflow_dispatch`).

```
push / pull request
  ├─ lint     black --check, flake8                         ─┐
  └─ test     PostgreSQL 17 (service) → makemigrations --check ├─► docker   збірка образу
              → pytest + покриття → htmlcov в артефакти       ─┘            push у Docker Hub (лише main)
              → coverage.svg у гілку badges (лише main)
```

- **lint:** ставить лише black і flake8 тих самих версій, що в
  `requirements-dev.txt`, і перевіряє весь код без змін (`--check --diff`).
- **test:** PostgreSQL — справжній контейнер (`services`), як локально; Redis
  не потрібен: тести беруть кеш у пам'яті, а задачі Celery виконуються одразу.
  `makemigrations --check` падає, якщо модель змінено без міграції. Покриття
  нижче 70% — теж помилка.
- **Бейдж покриття без Codecov:** `.github/scripts/coverage_badge.py` малює
  `coverage.svg` з відсотком (колір від червоного до зеленого), а крок CI кладе
  його в окрему гілку `badges` (одна версія, `--force`). README показує файл з
  `raw.githubusercontent.com`. Потрібен лише `permissions: contents: write`,
  жодних зовнішніх акаунтів і токенів.
- **docker:** чекає на `lint` і `test`. У pull request лише збирає образ (Dockerfile
  не зламано), у `main` — ще й відправляє `<DOCKERHUB_USERNAME>/hillel-bookstore`
  з тегами `latest` і `sha-<7 символів коміту>`. Шари кешуються між запусками (`gha`).
- **Налаштування репозиторію** (Settings → Secrets and variables → Actions):
  змінна `DOCKERHUB_USERNAME` і секрет `DOCKERHUB_TOKEN` (Docker Hub → Account
  settings → Personal access tokens, право Read & Write). Без них крок
  «Check the Docker Hub settings» пише, чого саме бракує.
- `concurrency`: новий push у ту саму гілку скасовує попередній запуск.

**pre-commit:** ті самі black і flake8 запускаються локально на кожен
`git commit` (лише для змінених файлів), тож помилку стилю видно ще до push.
Один раз після клонування:

```bash
pip install -r requirements-dev.txt
pre-commit install            # ставить хук у .git/hooks/pre-commit
pre-commit run --all-files    # перевірити весь проєкт
```

Якщо black щось переформатував, коміт зупиняється: перегляньте зміни,
`git add` і повторіть коміт. Помилки flake8 виправляються вручну. Версії в
`.pre-commit-config.yaml` збігаються з `requirements-dev.txt` (на це є тест
у `tests/unit/test_deploy.py`), тож хук і CI перевіряють однаково.

**CD:** Railway збирає образ із того самого репозиторію сам і чекає на CI
(«Wait for CI»): якщо тести впали, деплою не буде (див. «Деплой на Railway»).

## Деплой на Railway

```
GitHub (main) ── CI зелений ──► Railway: збірка з Dockerfile
                                   ├─ web      gunicorn + uvicorn, домен *.up.railway.app, Volume /app/media
                                   ├─ worker   celery worker -B (Beat усередині)
                                   ├─ flower   панель Celery, свій домен, вхід за логіном
                                   ├─ Postgres
                                   └─ Redis    кеш, сесії, черга Celery
```

Конфігурація — в інтерфейсі Railway, а не у файлі: `railway.json` / `railway.toml`
Railway оголосив застарілими (нові сервіси вже не можуть їх увімкнути).

**Сервіси:**

| Сервіс | Звідки | Команда запуску | Що ще |
|---|---|---|---|
| `web` | GitHub-репозиторій | з Dockerfile (`gunicorn config.asgi:application`) | Generate Domain; Healthcheck Path `/health/`; Volume → `/app/media`; Wait for CI |
| `worker` | той самий репозиторій | `celery -A config worker -B --loglevel=info --concurrency=2 --schedule=/tmp/celerybeat-schedule` | без домену, healthcheck і Volume; Wait for CI |
| `flower` | той самий репозиторій | `celery -A config flower --port=5555 --purge_offline_workers=60` | Generate Domain на порт 5555; Healthcheck Path `/healthcheck`; без Volume; Wait for CI |
| `Postgres` | шаблон Railway | — | дає `DATABASE_URL` |
| `Redis` | шаблон Railway | — | дає `REDIS_URL` |

- **Один образ — три сервіси.** `web`, `worker` і `flower` збираються з того самого
  коду, відрізняється лише команда, як `web`, `celery` і `flower` у `docker-compose.yml`.
- **Beat усередині worker** (`-B`): окремий сервіс для розкладу не потрібен.
  Beat має бути рівно один, тому у worker 1 репліка; інакше кожна задача за
  розкладом виконувалась би двічі. Перевірка в логах worker: `mingle: all alone`.
- **Міграції** робить лише `web`: `docker-entrypoint.sh` перед стартом gunicorn.
  Railway-команда worker замінює entrypoint, тож worker міграцій не запускає.
- **Volume і права.** Railway монтує Volume від імені root, а образ працює як
  `app`. Тому у web `RAILWAY_RUN_UID=0`: entrypoint стартує як root, віддає
  `/app/media` користувачу `app` і перезапускає себе вже як `app` (`setpriv`).
  Worker файлів не пише, тож працює одразу як `app`.

**Змінні** (Variables → Raw Editor; `${{...}}` — посилання Railway на інший сервіс):

| Змінна | web | worker |
|---|---|---|
| `DJANGO_SECRET_KEY` | новий ключ (не локальний) | той самий, що у web |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | те саме |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | те саме |
| `SITE_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | `https://${{web.RAILWAY_PUBLIC_DOMAIN}}` — домен **web**, у worker свого немає |
| `DJANGO_SERVE_MEDIA` | `True` | — |
| `RAILWAY_RUN_UID` | `0` | — |
| `WEB_CONCURRENCY` | `2` | — |
| `FLOWER_URL` | `https://${{flower.RAILWAY_PUBLIC_DOMAIN}}` (посилання в профілі; порожньо — посилання немає) | — |
| `STRIPE_SECRET_KEY` | `sk_test_...` | те саме |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` від webhook у Stripe Dashboard (не від Stripe CLI) | — |
| `BREVO_API_KEY`, `EMAIL_FROM` | так | так (листи відправляє саме worker) |
| `SENTRY_DSN`, `SENTRY_ENVIRONMENT=production` | так | так |
| `SENTRY_ISSUES_URL` | посилання в профілі | — |

Змінні `flower`:

| Змінна | Значення |
|---|---|
| `DJANGO_SECRET_KEY` | той самий, що у web (Flower завантажує налаштування Django) |
| `DATABASE_URL`, `REDIS_URL` | як у worker; Flower читає події задач з Redis |
| `FLOWER_BASIC_AUTH` | `логін:пароль`, новий довгий пароль, без коми; **обов'язково**: з Flower можна зупиняти задачі й воркерів, а домен публічний |
| `PORT` | `5555`: на цей порт Railway шле запити домену й перевірку здоров'я |

Flower сам читає змінні `FLOWER_*` як свої параметри (`FLOWER_BASIC_AUTH` =
`--basic-auth`), тому пароль не потрапляє в команду запуску. Команда Railway
замінює entrypoint, тож Flower, як і worker, міграцій не запускає.

**Перший запуск:**

```bash
brew install railway
railway login
railway link                                       # проєкт, середовище production, сервіс web
railway ssh --service web                          # shell у контейнері web, далі:
python manage.py createsuperuser
python manage.py seed_books                        # демо-каталог, якщо даних немає
python manage.py update_exchange_rates             # курси одразу, не чекаючи Beat
```

Без курсів сайт пропонує лише гривню; далі курси оновлює Beat у worker.

- **Stripe:** Dashboard (Test mode) → Developers → Webhooks → Add destination:
  Your account, payload **Snapshot** (код читає `event.data.object`), 4 події
  `checkout.session.*` (`completed`, `async_payment_succeeded`,
  `async_payment_failed`, `expired`), URL `https://<домен>/payments/webhook/stripe/`.
  Signing secret → `STRIPE_WEBHOOK_SECRET` у web.
- **Перенесення каталогу з локальної бази** (замість `seed_books`):
  ```bash
  docker compose exec -T web python manage.py dumpdata books.Category books.Author books.Publisher books.Book books.BookFormat books.BookCategory inventory.Warehouse inventory.Stock --indent 2 > catalog.json
  railway ssh --service web -- python manage.py loaddata --format=json - < catalog.json
  docker compose exec -T web tar -czf - -C /app/media covers | railway ssh --service web -- tar --no-same-owner -xzf - -C /app/media
  railway ssh --service web -- chown -R app:app /app/media
  ```
  `railway ssh` передає stdin у контейнер, тому файли не треба окремо копіювати.
  `loaddata` зберігає `id` книжок і сам скидає sequences PostgreSQL. Каталог на
  Railway перед цим має бути порожнім (інакше `id` перетнуться). Після
  завантаження варто очистити кеш (`cache.clear()`).

**Версія у футері.** Внизу кожної сторінки:
`Книгарня · домашнє завдання Hillel з Django · v1.1.0 (335de9f)`.

- `v1.1.0` — `__version__` у `config/version.py`, змінюється вручну раз на
  реліз (pull request у `main`): PATCH — виправлення, MINOR — нова можливість,
  MAJOR — зміна, що ламає старе (наприклад, API).
- `(335de9f)` — перші 7 символів задеплоєного коміту, посилання на нього в
  GitHub. Railway сам дає кожному деплою з GitHub змінну
  `RAILWAY_GIT_COMMIT_SHA`; деінде її можна задати як `APP_COMMIT`. Без змінної
  (локальний Docker, `runserver`) видно лише версію.
- Після злиття в `main` коміт у футері змінюється навіть тоді, коли версію не
  піднімали, тож одразу видно, що новий код уже на сайті.

**Перевірка після деплою:**

- у футері коміт збігається з останнім комітом `main` (`git log -1 --oneline origin/main`);
- `https://<домен>/health/` → `{"status": "ok", "database": "ok", "cache": "ok"}`;
- логи worker: `celery@... ready.`, `beat: Starting...`, `mingle: all alone`;
- `https://<домен flower>/` питає логін; після входу у Workers видно `celery@...`
  зі статусом Online, а в Tasks — задачі з моменту старту Flower;
- перемикач валюти в навбарі пропонує UAH, EUR, USD; `/api/currencies/` показує курси;
- обкладинка після Redeploy на місці (файли у Volume, а не в контейнері);
- тестова оплата карткою `4242 4242 4242 4242` (замовлення в гривнях і в доларах) →
  «Оплачено», у Stripe подія з відповіддю 200;
- `/sentry-debug/` (суперкористувач) → помилка в Sentry з `environment: production`.

## Redis

- **Кеш** (`CACHES`, `RedisCache`): один спільний для всіх worker-процесів gunicorn
  (`LocMemCache` за замовчуванням був би окремим у кожному процесі).
- **Сесії** (`SESSION_ENGINE = cached_db`): читаються з Redis, записуються і в
  Redis, і в PostgreSQL. Після перезапуску Redis ніхто не вилогінюється.
- **Черга Celery** — база 1 того самого Redis (`CELERY_BROKER_URL`): `FLUSHDB`
  кешу (база 0) не зачіпає задачі в черзі.

## Склад

Застосунок `inventory`. Кількість примірників — не поле книги, а окремі таблиці, і
лише для **паперового** формату: електронна книга й аудіокнига — файл, примірників
у них немає.

```
Warehouse: name, slug, is_default        # лише один склад за замовчуванням (UniqueConstraint з condition)
Stock:     format → BookFormat (CASCADE, лише paper), warehouse → Warehouse (PROTECT), quantity ≥ 0
           unique (format, warehouse)
```

- **Навіщо.** Книга й формат — це лише опис (назва, автор, ціна, обкладинка). Кожна
  покупка змінює `Stock`, а `Book` лишається незмінною, тому кеш книги не
  застаріває від продажів (див. «Кешування»).
- Продаж і повернення — зі складу за замовчуванням «General»
  (`Warehouse.objects.get_default()`).
- `Book.objects.with_stock()` — анотація `stock` (примірники паперового формату)
  одним підзапитом для всього списку; `BookFormat.objects.with_stock()` — те саме для
  форматів (кошик). Без неї `book.stock` робить один запит і запам'ятовує результат.
- `set_stock(книга або паперовий формат, кількість)`; для файлу — `ValueError`.
- `create_order()` блокує рядки `Stock` (`select_for_update`, у порядку `format_id`,
  щоб два замовлення не чекали одне на одного) і списує кількість;
  `cancel_order()` повертає її через `return_to_stock()` (`F("quantity") + n` у SQL).
- Новий паперовий формат одразу отримує рядок `Stock` з 0 (сигнал `post_save`).
- Щоденний звіт «малий залишок» — лише паперові формати в продажу.
- Права: `inventory.change_stock` — група Managers; Editors лише переглядають.
- Міграції перенесли дані: `inventory 0002` копіює `Book.stock` у `Stock`,
  `inventory 0003` переносить право `books.manage_stock` → `inventory.change_stock`,
  `books 0009` видаляє поле. Усі три мають зворотну операцію. Перенесення на
  паперовий формат — `inventory 0004`–`0006` (див. «Формати книг»).

## Кешування

Усе в Redis (база 0). Те, що залежить від користувача або змінюється з
кожною покупкою, **не кешується**.

| Що | Ключ | Скільки живе | Де |
|---|---|---|---|
| Об'єкт книги з автором і категоріями (без залишку) | `books:book:<pk>` | 1 година (`BOOK_CACHE_TIMEOUT`) | `books/cache.py`, `BookDetailView` |
| Фрагменти шаблонів: картка в каталозі, шапка й опис книги | `book_card` / `book_detail_header` / `book_detail_body` + `pk` + мова | 1 година | `{% cache %}` у `book_list.html`, `book_detail.html` |
| `GET /api/authors/`, `/api/publishers/`, `/api/categories/` | `api:<покоління>:...` | 10 хвилин (`API_CACHE_TIMEOUT`) | `api/cache.py` |

- **Не в кеші:** залишок і бейдж наявності, CSRF-токен, кнопки «в кошик» і
  кнопки менеджера. Закешований CSRF-токен одного відвідувача дав би іншим 403,
  а кнопки менеджера побачив би покупець.
- **`/api/books/` не кешується:** у відповіді є `stock`, він змінюється з кожною покупкою.
- **Очищення — сигнали** (`books/signals.py`): `post_save` / `post_delete` книги,
  автора (усі його книги), видавництва (усі його книги), категорії (усі її книги),
  `BookCategory` і `m2m_changed`.
  Ключі видаляються одразу і ще раз після `COMMIT`: інакше паралельний запит
  міг би встигнути покласти в кеш старі дані з бази.
- **API — «покоління»:** ключі `cache_page` залежать від URL і параметрів
  (`?page=2`, `?search=`), перелічити їх усі неможливо. Тому в кожному ключі є
  номер покоління, і будь-яка зміна каталогу робить `incr` — старі ключі
  більше не читаються й зникають самі через 10 хвилин. Без `FLUSHDB`: сесії
  в тій самій базі Redis лишаються.
- **Логи:** `DEBUG Book cache hit: id=7`, `DEBUG Book cache miss: id=7, cached for 3600 s`,
  `INFO Book cache cleared: ids=[7] (7 keys), reason: Book saved` (1 об'єкт +
  3 фрагменти × 2 мови), `INFO API cache: new generation, old answers are not used (...)`.

## Celery

```
web / admin ── enqueue_on_commit(task, pk) ──► Redis db 1 ──► celery (worker) ──► SMTP / база
celery-beat ── за розкладом ─────────────────┘
```

**Задачі:**

| Задача | Хто ставить | Що робить |
|---|---|---|
| `send_order_created_email_task` | `create_order()` | лист «замовлення створено» |
| `send_payment_received_email_task` | оплата (webhook, менеджер) | лист «оплату отримано» |
| `send_order_cancelled_email_task` | автоматичне скасування | лист «замовлення скасовано» (покупцю, який сам натиснув «Скасувати», не надсилається) |
| `cancel_unpaid_orders` | Beat, щогодини о :00 | `new` + `unpaid` старші за `ORDER_UNPAID_MAX_AGE_HOURS` (24) → скасування, книги на склад |
| `clear_expired_sessions` | Beat, 03:00 UTC | `manage.py clearsessions` |
| `send_daily_report` | Beat, 06:00 UTC | звіт за вчора менеджерам (група Managers), виручка в гривнях |
| `update_exchange_rates` | Beat, 6:05 і 13:05–17:05 UTC щогодини | курси НБУ на сьогодні й завтра (див. «Валюти») |

- **Після `COMMIT`.** `enqueue_on_commit()` (`config/celery.py`) ставить задачу
  лише після успішної транзакції: воркер не прочитає замовлення, якого ще немає
  в базі. Якщо Redis недоступний, задача виконується одразу в цьому ж процесі
  (лист не губиться).
- **Повторні спроби листів:** при `OSError` (SMTP недоступний) — ще 3 спроби,
  паузи до 60, 120, 240 с (`retry_backoff`; `retry_jitter` бере випадкову
  частину, щоб сотня листів не повторювалась в ту саму секунду). Після
  останньої — помилка в лозі й у Sentry.
- **Надійність:** `acks_late` (повідомлення видаляється з черги після виконання:
  перезапуск воркера задачу не губить), `prefetch 1`, ліміт часу 5 / 6 хвилин.
- **Звіт** (`orders/reports.py`): 3 CSV у вкладенні (UTF-8 з BOM, відкриваються
  в Excel): замовлення дня, топ книг, книги з залишком ≤ 5. Менеджери в `bcc`,
  кожному — його мовою.
- Розклад — у `CELERY_BEAT_SCHEDULE` (`config/settings/base.py`), а не в адмінці
  (django-celery-beat): його видно й рев'юють у git. Час — UTC.
- Ручний запуск задачі:
  `docker compose exec web python manage.py shell -c "from orders.tasks import send_daily_report; send_daily_report.delay()"`.

### Flower

http://localhost:5555/ (на Railway — домен сервісу `flower`) — панель Celery:
воркери, кожна задача з аргументами, станом, часом виконання, помилкою й
повторними спробами, графіки.

- Воркер надсилає події кожного кроку задачі (`CELERY_WORKER_SEND_TASK_EVENTS`,
  `CELERY_TASK_SEND_SENT_EVENT`), Flower читає їх з Redis.
- Логін обов'язковий (`FLOWER_BASIC_AUTH`; без нього `docker compose` не
  стартує): з Flower можна зупиняти задачі й воркерів. Порт відкрито лише на
  `127.0.0.1`, не для інших пристроїв у мережі.
- Історія — в пам'яті Flower: після перезапуску видно задачі з цього моменту.

## nginx

`nginx/default.conf`, образ `nginx:1.30-alpine`, порт 8000 на Mac.

```
браузер → localhost:8000 → nginx :80 ─┬─ /static/ → volume static_data       (Cache-Control: рік, immutable)
                                       ├─ /media/  → volume media_data        (expires 7d, nosniff)
                                       └─ решта    → web:8000 (gunicorn)
```

- **Навіщо:** файли з диска nginx віддає набагато швидше за Python, а
  повільних клієнтів тримає на себе — воркери gunicorn не чекають на них.
- `client_max_body_size 3m`: за замовчуванням 1 МБ, і обкладинка на 2 МБ
  отримала б від nginx 413 ще до перевірки у формі. Ще `gzip` для HTML, CSS, JS, JSON.
- `proxy_set_header Host $http_host` — з портом (`localhost:8000`): Django
  звіряє його з `Origin` у POST, без порту перевірка CSRF давала б 403.
- **Справжня IP-адреса клієнта.** nginx **записує** (а не дописує) `X-Forwarded-For
  $remote_addr`, gunicorn запущено з `--forwarded-allow-ips=*` (запити приходять
  лише від nginx), і uvicorn кладе адресу в `REMOTE_ADDR`. Тому логи входу
  й ліміти API бачать клієнта, а не nginx, без змін у коді.
- DRF `NUM_PROXIES: 0`: ліміт анонімних запитів рахується за `REMOTE_ADDR`, а не
  за `X-Forwarded-For` з запиту — інакше клієнт обходив би ліміт вигаданою адресою.
- **`DEBUG=False` у Docker:** немає сторінок з traceback і Debug Toolbar.
  Помилки показують `404.html`, `403.html`, `500.html`; `500.html` не наслідує
  `base.html` — він рендериться без контексту запиту й не повинен сам упасти.
- nginx лише для локального `docker compose`. На Railway його немає: статику
  роздає WhiteNoise, обкладинки — `serve_media` (див. «Статичні файли і media»).

## Sentry

`config/sentry.py`, викликається в кінці `config/settings/base.py`, тож працює в `web`,
`celery` і `celery-beat`. Без `SENTRY_DSN` (і в тестах) не запускається.

**Що потрапляє в Sentry:**

- виняток у view (користувач бачить `500.html`) — з URL, методом, заголовками;
- виняток у задачі Celery після **останньої** повторної спроби;
- `logger.error()` / `logger.exception()`; рядки INFO і WARNING — як «breadcrumbs»
  (кроки перед помилкою);
- таймінги 10% запитів і задач (`SENTRY_TRACES_SAMPLE_RATE`), задача — разом із
  запитом, що її поставив. `/health/` не вимірюється: Docker смикає його кожні
  10 секунд, це з'їдало б квоту.

**Що не потрапляє** (`data_collection` — заміна `send_default_pii`, застарілого в 2.74):

- cookies взагалі (`sessionid` дав би змогу увійти від імені користувача);
- дані користувача (id, email, IP) і заголовки з IP; `Authorization` (JWT) SDK замінює на `[Filtered]`;
- тіла запитів (у формі оформлення — ім'я, телефон, адреса), значення параметрів SQL;
- рядки логів входу та видачі токена (в них IP);
- `Invalid HTTP_HOST header` від ботів.

**Перевірка:** суперкористувач відкриває `/sentry-debug/` — це навмисний
`ZeroDivisionError` (для інших 404). Чи ввімкнено Sentry у контейнері:

```bash
docker compose exec web python manage.py shell --no-imports -c "import sentry_sdk as s; c = s.get_client(); print(c.is_active(), c.options['environment'])"
# True docker
# на Railway те саме: railway ssh --service web, потім команда без "docker compose exec web" -> True production
```

`tests/unit/test_sentry.py` шле запит через справжній `config.asgi.application`
(звичайний тестовий `Client` обходить місце, де SDK збирає дані запиту) і
перевіряє, що ні `sessionid`, ні IP, ні email у подію не потрапили.

## `/health/`

`config/views.py`, async view: `await ContentType.objects.aexists()` у PostgreSQL і
`cache.aset` / `aget` / `adelete` випадкового значення під **випадковим ключем** у Redis.

```
200 {"status": "ok", "database": "ok", "cache": "ok"}
503 {"status": "error", "database": "ok", "cache": "error"}
```

- 503, а не 500: Django працює, недоступний сервіс, від якого він залежить.
- Ключ кешу випадковий для кожної перевірки: зі спільним ключем одночасні
  перевірки перезаписували значення одна одної, і під навантаженням (50
  паралельних запитів під ASGI) справний Redis давав 503.
- Подробиці помилки пишуться тільки в лог (`config.views`), не у відповідь.
- `@never_cache`, `@require_GET`; сесію не читає, тому працює й без Redis.
- Перевірено: `docker compose stop redis` → 503, `web` за ~30 с стає `unhealthy`;
  `docker compose start redis` → знову `healthy` без перезапуску `web`.
  Docker compose сам `unhealthy`-контейнери не перезапускає, лише показує стан.

## Management-команди

### `seed_books`

Створює 5 категорій, 10 авторів і 12 книг з характеристиками (видавництво, мова, рік)
і форматами (17 форматів: частина книг паперова, електронна й аудіокнига водночас,
кілька — лише електронна чи аудіо, кілька цін у USD і EUR; приблизні значення для
фільтрів, а не точні реальні видання). Команду можна запускати повторно, дублікати не
створюються: книгам, що вже є, команда заповнює лише порожні характеристики, а
формати додає лише книзі без жодного формату, тож введене менеджером лишається.

```bash
python manage.py seed_books
```

### `update_exchange_rates`

Завантажує курси НБУ для активних валют (див. «Валюти» → «Курси НБУ»). Без
параметрів — на сьогодні й найновіший день, `--date РРРР-ММ-ДД` — на один день.

```bash
python manage.py update_exchange_rates
python manage.py update_exchange_rates --date 2026-11-13
```

### `cancel_unpaid_orders`

Скасовує старі замовлення `new` + `unpaid` і повертає їхні книги на склад
(через `cancel_order()`; відкрита сторінка Stripe теж закривається).

```bash
python manage.py cancel_unpaid_orders                    # старші за 24 години
python manage.py cancel_unpaid_orders --older-than 12h   # 30m, 12h, 2d
python manage.py cancel_unpaid_orders --dry-run          # лише показати
```

- `cancel_order(only_unpaid=True)` перевіряє «ще не оплачено» вже під блокуванням:
  якщо оплата прийшла між вибіркою й скасуванням, замовлення пропускається («skipped»).
- Мінімум `--older-than 30m`: сторінка Stripe живе 31 хвилину, молодше замовлення
  може саме зараз оплачуватися.
- Щогодини запускається задачею Celery Beat (`orders.tasks.cancel_unpaid_orders`);
  кожному покупцю — лист «замовлення скасовано». Кожен запуск, навіть без
  скасувань, пише в лог `Unpaid orders older than 1 day, 0:00:00: cancelled 0, skipped 0`.

### `book_stats`

Виводить статистику книгарні та демонструє можливості ORM. Ціна книги — ціна «від»
у гривнях (найдешевший формат у продажу, `with_display_price`), «в наявності» —
`with_availability()`, вартість запасу — за ціною паперового формату.

1. **filter**:
   - у наявності й дешевші за задану ціну;
   - мало на складі, немає на складі;
   - книги певної категорії, книги без категорії;
2. **Q-об'єкти**:
   - пошук за назвою / автором / категорією (OR);
   - «у наявності, але не в категорії» (AND + NOT);
   - складна умова для акції;
3. **annotate**:
   - статистика по категоріях;
   - топ-5 книг за вартістю запасу (`F("paper_price_uah") * F("stock")`);
   - категорії з понад 2 книгами (HAVING);
4. **aggregate**: підсумок по всьому магазину.

```bash
python manage.py book_stats
python manage.py book_stats --max-price 200 --search кінг --category fentezi
python manage.py book_stats --sql   # також показати згенерований SQL
```

| Параметр | За замовчуванням | Опис |
|---|---|---|
| `--max-price` | `300` | максимальна ціна для фільтра |
| `--search` | `Кінг` | рядок пошуку для Q-запиту |
| `--category` | `fentezi` | slug категорії |
| `--sql` | | друкувати SQL кожного запиту |

## Кирилиця в PostgreSQL

**Пошук.** `icontains` на PostgreSQL — це `UPPER(title) LIKE UPPER('%вбив%')`, і
`UPPER` для кирилиці працює правильно. Тому `books/sqlite_functions.py` з ДЗ №16
(власний `LIKE` для SQLite) видалено.

**Сортування.** Образ `postgres:17-alpine` за замовчуванням створює базу з
collation libc (`en_US.utf8`, провайдер `c`). Але musl (бібліотека C в Alpine)
не має правил сортування для мов, тому рядки порівнювались за кодами Unicode,
як у SQLite:

```
Є (U+0404)  І (U+0406)  Ї (U+0407)  А…Я (U+0410–042F)  а…я (U+0430–044F)  Ґ (U+0490)
ORDER BY:  Євген, Іван, Ївга, Андрій, Борис, …, Яна, андрій, Ґанна
```

Рішення — ICU (бібліотека з правилами сортування для мов, вбудована в образ):

```yaml
POSTGRES_INITDB_ARGS: "--locale-provider=icu --icu-locale=uk-UA"
```

```
ORDER BY:  андрій, Андрій, Борис, Гліб, Ґанна, Євген, Ирина, Іван, Ївга, Яна
```

- Діє на всю базу: моделі й `order_by` не змінювались.
- `initdb` виконується лише на порожньому volume. Щоб застосувати до існуючої
  бази: `docker compose down`, `docker volume rm hillel_bookstore_postgres_data`,
  `docker volume create hillel_bookstore_postgres_data`, `docker compose up -d` і знову
  `loaddata` (volume обкладинок не чіпаємо).
- Перевірка: `SELECT datlocprovider FROM pg_database WHERE datname = current_database()`
  повертає `i` (ICU).

## Відомі обмеження

- **Старі файли обкладинок не видаляються.** Django не прибирає файл з
  диска, коли книгу видалено, обкладинку замінено або позначено «Remove».
  Такі файли лишаються в `media/` (у Docker — у volume `media_data`).
- **IP у логах — це адреса Mac з погляду Docker** (`192.168.65.1`): nginx
  передає справжню адресу клієнта, але на локальній машині клієнт — сам Docker Desktop.
- **Локально лише HTTP.** HTTPS увімкнено на Railway (сертифікат дає Railway,
  див. «Налаштування»); локальний `docker compose` працює з `DJANGO_HTTPS=False`.
- **Пошта на Railway — лише через Brevo.** SMTP на Free / Trial / Hobby
  заблокований, тому Gmail там не працює; без `BREVO_API_KEY` листи лише
  друкуються в лог worker. Безкоштовний тариф Brevo має денний ліміт листів.
- **Обкладинки на Railway роздає Django** (`serve_media`), а не окремий сервер
  файлів: для кількох десятків обкладинок досить, для великого каталогу краще
  сховище на кшталт S3.
- **Історія Flower і розклад Beat не зберігаються** між перестворенням контейнерів:
  Flower тримає задачі в пам'яті, Beat — час останніх запусків у `/tmp`
  (пропущений запуск не повторюється, просто чекає наступного).
- **`logs/app.log` у контейнері не зберігається** між перестворенням контейнера
  (немає volume); у Docker логи дивимось через `docker compose logs`.
- **Вихід у лозі middleware показується як `user=anonymous`**: `logout()`
  змінює `request.user` раніше, ніж middleware його читає. Хто вийшов, видно в
  рядку `Logout: user=...` від сигналу.
- **Немає скидання пароля й підтвердження email.** Відправка листів уже є,
  лишилось підключити `PasswordResetView`; заплановано.
- **Цифрові формати поки з доставкою.** Електронна книга й аудіокнига не мають
  складу й завжди доступні, але замовлення все одно просить адресу, а файл не
  видається (див. «Плани»).
- **Курси лише НБУ.** Комісії й курси банку не враховуються: ціна в доларах — це
  ціна в гривнях за офіційним курсом. У вихідні й свята НБУ курс не змінює, сайт
  бере останній відомий.
- **Валюту замовлення не можна змінити** після оформлення: щоб заплатити в іншій
  валюті, замовлення скасовують і оформлюють заново.
- **Сортування замовлень за сумою в адмінці** — за числом, без перерахування:
  100 $ і 100 ₴ стоять поруч. Звіти рахують у гривнях.
- **Онлайн-оплата лише у валютах з копійками** (UAH, USD, EUR тощо): для JPY чи KWD
  потрібне інше округлення сум.
- **Stripe лише в тестовому режимі.** Акаунт не активовано (Україна не підтримується).
- **Повернення коштів вручну.** Якщо скасовано оплачене замовлення, адмінка лише
  попереджає «return the money to the customer»; refund через Stripe API немає.
- **Скасування менеджером в адмінці — без листа покупцю.** Лист «замовлення
  скасовано» йде лише при автоматичному скасуванні.
- **Дані не перекладаються.** Інтерфейс двомовний, але назви й описи книг,
  імена авторів і категорії зберігаються однією мовою (так, як їх внесли).
- **Сторінка Stripe не українською.** Stripe Checkout не має української:
  для `uk` передається `locale="auto"` (мова браузера), для `en` — `"en"`.
- **JWT не можна відкликати.** Виданий токен дійсний до кінця терміну (access —
  15 хвилин, refresh — 1 день) навіть після зміни пароля; «вийти» з API — це
  забути токени на клієнті. Відкликання — `token_blacklist` simplejwt (див. «Плани»).
- **Обкладинки й оплата — лише на сайті.** API віддає адресу обкладинки, але не
  приймає файл (перевірки розміру й типу — у `BookForm`; див. «Плани»); оплата — через
  `site_url` замовлення.
- **Асинхронний ORM Django 6.1 — обгортка.** Запити до бази все одно йдуть у
  потоці (`sync_to_async`); виграш у тому, що event loop не чекає на них.

## Плани

- обмеження частоти запитів у nginx (`limit_req`) для сторінок сайту;
- переклад даних: назви й описи книг, автори, категорії українською та англійською
  (django-modeltranslation або django-parler);
- скидання пароля й підтвердження email;
- лист покупцю, коли замовлення скасовує менеджер в адмінці;
- відкликання JWT: `token_blacklist` simplejwt — вихід з API (`POST /api/token/logout/`
  кладе refresh у чорний список), `ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION`,
  недійсні токени після зміни пароля; потрібна міграція;
- завантаження обкладинки через API: `multipart/form-data` у `POST` / `PATCH /api/books/`
  з тими самими перевірками, що в `BookForm` (JPG / PNG / WebP, до 2 МБ, справжнє зображення);
- видача електронної книги й аудіокниги: файл або посилання після оплати й
  замовлення без адреси доставки, якщо в ньому лише цифрові формати;
- список бажань: кнопка «♡» на картці й сторінці книги, сторінка зі збереженими книгами
  в профілі;
- рейтинг книги: оцінка від 1 до 5 від покупця, середня оцінка й кількість оцінок
  на картці та сторінці книги, сортування каталогу за рейтингом;
- сторінка книги: збільшення обкладинки при натисканні (модальне вікно).
