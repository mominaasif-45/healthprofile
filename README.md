# HealthProfile

## Problem statement

People need a private place to keep a wellness profile (goals, contact preference, emergency
contact), and clinic staff need a secure way to search and review those profiles. The two groups
must never be mixed up: members and admins sign in through **two separate auth systems**, so a
member can never reach an admin feature, even by tampering with the browser. All data in this
project is synthetic.

> **Demo environment.** Every profile is synthetic. No real patient data. Wellness goals only,
> never diagnoses or medical advice.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Django 6 + Django REST Framework | Sessions, CSRF, password hashing and migrations built in |
| User auth | `simplejwt` + token blacklist | Logout really revokes the refresh token |
| Admin auth | Django server-side sessions | Expires after 30 minutes idle, deleted server-side on logout |
| Database | PostgreSQL | Real `EXPLAIN` plans, DB-level constraints |
| Frontend | Next.js (App Router) + TypeScript | Proxies `/api/*` to Django, so the browser sees one origin |
| API docs | drf-spectacular (Swagger at `/api/docs/`) | Click-through, testable docs |
| Tests | pytest + pytest-django (+ freezegun) | 56 short tests |

## Architecture

```
Browser ──► Next.js :3000 ──(rewrite /api/*)──► Django :8000 ──► PostgreSQL
```

* One origin for the browser, so `SameSite=Lax` cookies work with no CORS setup.
* **Users:** `POST /api/auth/user/login/` sets two **HttpOnly** cookies: `access` (15 min) and
  `refresh` (1 day, only sent to `/api/auth/user/`). The frontend calls `/refresh/` once on a 401
  and retries. Logout blacklists the refresh token. The JWT holds only `user_id`, `exp`, `jti`,
  `token_type`; the role always comes from the database.
* **Admins:** created only with `python manage.py create_admin`. `POST /api/admin/login/` starts a
  session (`sessionid`, HttpOnly, 30 min idle). Every admin view accepts **only** session auth and
  the `IsAdminRole` permission, so a user JWT gets **403** on admin routes.
* **CSRF:** the JWT also lives in a cookie, so every state-changing request (user *and* admin)
  needs the `X-CSRFToken` header. Only the **admin** login calls Django's `login()`, which rotates
  the CSRF token, so the frontend re-fetches `/api/csrf/` right after an admin signs in. The user
  JWT login does not call `login()` and does not rotate the token.
* **No IDOR by design:** users only have `/api/profiles/me/`. There is no `/profiles/{id}/` route.
* All errors share one shape: `{"error": {"code", "message", "fields"}}`.

### Database

```mermaid
erDiagram
    USER ||--o| HEALTH_PROFILE : "owns (1 to 0..1)"
    USER ||--o{ OUTSTANDING_TOKEN : "issued JWT refresh"
    OUTSTANDING_TOKEN ||--o| BLACKLISTED_TOKEN : "revoked at logout"
    USER ||--o{ DJANGO_SESSION : "admin sessions"
    USER {
        bigint id PK
        varchar email "unique, lower-case (CHECK)"
        varchar name
        varchar password "hash only"
        varchar role "user | admin (CHECK)"
        bool is_active
    }
    HEALTH_PROFILE {
        bigint id PK
        bigint user_id FK "unique, ON DELETE CASCADE"
        varchar full_name
        date date_of_birth "nullable"
        varchar age_range "nullable"
        varchar contact_preference "email | phone | sms"
        jsonb wellness_goals "list of short labels"
        text allergies
        varchar emergency_contact_name
        varchar emergency_contact_phone
        text lifestyle_notes
        varchar status "active | deactivated"
        timestamptz created_at
        timestamptz updated_at
    }
```

Constraints: lower-case email, valid role/status/contact preference, and a profile needs a date of
birth **or** an age range.
`wellness_goals` is a JSON list (instead of free text) so the UI can render goal chips.

### Indexes

| Index | Query it serves |
|---|---|
| unique `email` (+ lower-case CHECK) | login and signup lookups, blocks `Ali@x.com` vs `ali@x.com` |
| unique `user_id` (from OneToOne) | `GET /profiles/me/` |
| `(status, created_at DESC)` | admin list filtered with `?status=`: `WHERE status = … ORDER BY created_at DESC` |

The optional trigram index on `full_name` was left out (it needs the `pg_trgm` extension).

### EXPLAIN demo

```bash
python manage.py seed_profiles --bulk 1000
python manage.py shell -c "from profiles.models import HealthProfile as H; print(H.objects.filter(status='active').order_by('-created_at').explain(analyze=True))"
```

Real output with 1,006 profiles (891 active):

```text
Sort  (cost=28.66..28.90 rows=96 width=145) (actual time=0.842..0.883 rows=891 loops=1)
  Sort Key: created_at DESC
  Sort Method: quicksort  Memory: 170kB
  ->  Seq Scan on profiles_healthprofile  (cost=0.00..25.50 rows=96 width=145) (actual time=0.016..0.327 rows=891 loops=1)
        Filter: ((status)::text = 'active'::text)
        Rows Removed by Filter: 115
Planning Time: 0.348 ms
Execution Time: 0.954 ms
```

The index was **not** used here: about 89% of the rows are `active`, so reading almost the whole
table and sorting it is cheaper for Postgres than walking the index.

The same query for a selective value (`status='deactivated'`, 115 rows) does use the index:

```text
Index Scan using profile_status_created_idx on profiles_healthprofile  (cost=0.27..8.29 rows=1 width=145) (actual time=0.128..0.252 rows=115 loops=1)
  Index Cond: ((status)::text = 'deactivated'::text)
Planning Time: 4.123 ms
Execution Time: 0.356 ms
```

## Features

* Sign up (name, email, password strength meter), sign in, sign out
* Create / edit my profile, profile-strength meter, wellness goal chips, add custom goals
* Owner cannot edit a profile once an admin deactivated it (403)
* Admin portal: search by name or email, filter by status, pagination, detail panel,
  full profile page, deactivate with confirmation
* **Light and dark themes**, following the system setting with a manual toggle
* Responsive: single column on mobile

## Run it locally

Prerequisites: Python 3.13, PostgreSQL, Node 20+.

```bash
# 1) Backend  (terminal 1)
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1          # Windows PowerShell
pip install -r requirements.txt
cp .env.example .env                  # then edit DATABASE_URL, SECRET_KEY, JWT_SIGNING_KEY
python manage.py migrate
python manage.py seed_profiles        # 5 demo members, password: CalmMorning2026
python manage.py create_admin --email admin@healthprofile.test --name "Clinic Admin"
python manage.py runserver            # http://127.0.0.1:8000  (Swagger: /api/docs/)

# 2) Frontend (terminal 2)
cd frontend
npm install
npm run dev                           # http://localhost:3000
```

Pages: `/signup`, `/login`, `/profile`, `/admin/login`, `/admin`, `/admin/profiles/[id]`.

## Environment configuration

Real secrets live only in `backend/.env`, which is **git-ignored** and never committed. The
committed `backend/.env.example` and `frontend/.env.example` contain placeholders only; copy them
and fill in your own values.

| File | Variable | What it does |
|---|---|---|
| `backend/.env` | `DEBUG` | `True` for local development. When `False`, cookies are marked `Secure` (HTTPS only). Defaults to `False` if unset. |
| `backend/.env` | `SECRET_KEY` | Django's secret key (sessions, CSRF). Use a long random value. |
| `backend/.env` | `JWT_SIGNING_KEY` | Key that signs the user JWTs. Keep it different from `SECRET_KEY`. |
| `backend/.env` | `DATABASE_URL` | PostgreSQL connection string, e.g. `postgres://user:password@localhost:5432/healthprofile`. |
| `backend/.env` | `ALLOWED_HOSTS` | Comma-separated hostnames Django will serve. Defaults to `localhost,127.0.0.1`. |
| `backend/.env` | `CSRF_TRUSTED_ORIGINS` | Comma-separated origins allowed to send CSRF-protected requests (the Next.js frontend). Defaults to `http://localhost:3000,http://127.0.0.1:3000`. |
| `frontend/.env` | `BACKEND_URL` | Where Next.js forwards `/api/*` calls. Defaults to `http://127.0.0.1:8000`. |

## Tests

```bash
cd backend
python -m pytest
```

Covers signup, user JWT (expired, tampered, blacklisted, throttled), profiles (own-data only,
partial update, validation, 409), and admin (403 for user JWTs, session list/search/detail, CSRF on
deactivate, logout destroys the session row).

## API examples

Full interactive docs: **http://127.0.0.1:8000/api/docs/**

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/csrf/` | none | Sets the `csrftoken` cookie |
| POST | `/api/auth/signup/` | none | Register → 201 / 400 / 409 |
| POST | `/api/auth/user/login/` | CSRF | Sets `access` + `refresh` cookies |
| POST | `/api/auth/user/refresh/` | refresh cookie + CSRF | Rotates tokens |
| POST | `/api/auth/user/logout/` | cookie + CSRF | Blacklists refresh, clears cookies |
| GET | `/api/auth/me/` | JWT | Current user |
| POST / GET / PATCH | `/api/profiles/me/` | JWT (+ CSRF on writes) | Create / read / update my profile |
| POST | `/api/admin/login/` | CSRF | Starts an admin session (403 for non-admins) |
| POST | `/api/admin/logout/` | session + CSRF | Ends the session on the server |
| GET | `/api/admin/me/` | session | Current admin |
| GET | `/api/admin/profiles/?search=&status=&page=` | session + admin | List / search |
| GET | `/api/admin/profiles/{id}/` | session + admin | One profile |
| POST | `/api/admin/profiles/{id}/deactivate/` | session + admin + CSRF | Deactivate |

```http
POST /api/auth/user/login/
{ "email": "momina.asif@example.com", "password": "CalmMorning2026" }

200 OK   (Set-Cookie: access=…; HttpOnly; SameSite=Lax, refresh=…; HttpOnly; Path=/api/auth/user/)
{ "id": 1, "name": "Momina Asif", "email": "momina.asif@example.com", "role": "user", "date_joined": "…" }
```

```http
PATCH /api/profiles/me/        (X-CSRFToken header required)
{ "allergies": "Peanuts" }

200 OK
{ "full_name": "Momina Asif", "age_range": "25-34", "allergies": "Peanuts",
  "status": "active", "completeness": { "percent": 80, "missing": ["Add an emergency contact"] }, … }
```

```http
POST /api/auth/signup/
{ "name": "Sara", "email": "sara@example.com", "password": "short" }

400 Bad Request
{ "error": { "code": "validation_error", "message": "Invalid input.",
             "fields": { "password": ["This password is too short. It must contain at least 10 characters."] } } }
```

Status codes: 400 invalid input, 401 not logged in / token expired, 403 not allowed (including
missing CSRF), 404 not found, 409 duplicate email or profile, 429 login throttled (5 per minute).

## Screenshots

| | |
|---|---|
| ![Sign up](docs/screenshots/signup.png) | ![My profile (light)](docs/screenshots/profile.png) |
| Sign up | My profile, light mode |
| ![My profile (dark)](docs/screenshots/profile-dark.png) | ![Admin list](docs/screenshots/admin.png) |
| My profile, dark mode | Admin: member list |
| ![Admin detail](docs/screenshots/admin-detail.png) | ![HttpOnly cookies](docs/screenshots/cookies.png) |
| Admin: full profile | `access` / `refresh` / `sessionid` cookies are HttpOnly |
| ![Swagger](docs/screenshots/swagger.png) | ![pytest](docs/screenshots/pytest.png) |
| Swagger API docs | pytest run |

## AI workflow

How AI was used to plan, build, review and debug this project, including prompt iterations, blast
radius control, a manual security review and a bug story: see
[docs/ai-workflow.md](docs/ai-workflow.md).

## Demo video

https://www.loom.com/share/7f3a96d221f1415b9c2abe2070b3f38e

## Limitations

* Intended for local development: set `DEBUG=False` and HTTPS for production (cookies then become `Secure`).
* No password reset, email verification or profile reactivation yet.
* The "Renews in N min" label is an estimate from when the page last saw a login or refresh, because the
  token cookies are HttpOnly and cannot be read by JavaScript.
