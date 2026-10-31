# HealthProfile

## Problem statement

People need a private place to keep a wellness profile, and clinic staff need a secure way to search and
review those profiles. The two groups must never be mixed up: members and admins sign in through **two
separate auth systems**, so a member can never reach an admin feature, even by tampering with the browser.
Every edit and every admin action is recorded in an **audit trail** that stores field names, never values.
All data in this project is synthetic.

> **Demo environment.** Every profile is synthetic. No real patient data. Wellness goals only,
> never diagnoses or medical advice.

## What is new in Week 2

Week 2 ("Role-Based Health Profiles and Database Engineering") extends the Week 1 app; nothing was rebuilt.
The single `HealthProfile` table was split into **normalized sections** (demographics, emergency contacts,
wellness preferences + goals), a stored **completion status**, a full member **CRUD** API, an
append-only **audit trail**, richer **admin filtering and ordering**, **hidden sensitive fields** for admins,
and justified **composite indexes** with real `EXPLAIN` evidence.

### Feature checklist

Week 1 (kept working and re-verified by tests):

- [x] Self-service signup and JWT login (HttpOnly cookies, 15-min access, 1-day refresh, rotation + blacklist)
- [x] Admins created only with `manage.py create_admin`; session login, 30-min idle expiry, CSRF on writes
- [x] Hashed passwords, login throttling (5/min), CSRF on every cookie-based write
- [x] No member route with another profile's id; a member JWT gets 403 on every admin route
- [x] Swagger docs, one error shape, light and dark themes

Week 2 (the assignment):

- [x] **Profile sections as related tables**: demographics, emergency contacts, wellness preferences + goals, completion status
- [x] **User-owned CRUD** on every section, including `DELETE` (a single contact, or the whole profile)
- [x] **Audit events** for member edits and admin actions: who, what, which fields changed, outcome, request id. No secrets, no values
- [x] **Admin-only listing and search** with pagination, filters (status, completion, created dates, search) and ordering
- [x] **Sensitive fields hidden** from admin responses (date of birth, allergies, lifestyle notes; phones masked)
- [x] **Foreign keys, unique constraints and composite indexes** justified by real queries, with `EXPLAIN (ANALYZE, BUFFERS)` evidence
- [x] **Admin reactivate** and per-profile **history** endpoint
- [x] **Role-boundary tests**: 262 backend tests, including every route checked for member / admin / signed-out access
- [x] **Migrations** with a data migration that moves existing Week 1 data into the new tables
- [x] Updated **Swagger** (tags, descriptions, examples), README, `CLAUDE.md` project rules

## Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Django 6 + Django REST Framework | Sessions, CSRF, password hashing and migrations built in |
| User auth | `simplejwt` + token blacklist | Logout really revokes the refresh token |
| Admin auth | Django server-side sessions | Expires after 30 minutes idle, deleted server-side on logout |
| Database | PostgreSQL | Real `EXPLAIN` plans, partial unique indexes, DB-level constraints |
| Frontend | Next.js (App Router) + TypeScript | Proxies `/api/*` to Django, so the browser sees one origin |
| API docs | drf-spectacular (Swagger at `/api/docs/`) | Click-through, testable docs |
| Tests | pytest + pytest-django (+ freezegun); Vitest + Testing Library | 262 backend tests, 11 frontend tests |

## Architecture

```
Browser ──► Next.js :3000 ──(rewrite /api/*)──► Django :8000 ──► PostgreSQL
```

* One origin for the browser, so `SameSite=Lax` cookies work with no CORS setup.
* **Members:** `POST /api/auth/user/login/` sets two **HttpOnly** cookies: `access` (15 min) and `refresh`
  (1 day, only sent to `/api/auth/user/`). The frontend calls `/refresh/` once on a 401 and retries. Logout
  blacklists the refresh token. The JWT holds only `user_id`, `exp`, `jti`, `token_type`; the role is always
  read from the database.
* **Admins:** created only with `python manage.py create_admin`. `POST /api/admin/login/` starts a session
  (`sessionid`, HttpOnly, 30 min idle). Every admin view accepts **only** session auth plus the `IsAdminRole`
  permission, so a member JWT gets **403** on admin routes, and an admin session gets 401 on member routes.
* **CSRF:** the JWT also lives in a cookie, so every state-changing request (member *and* admin) needs the
  `X-CSRFToken` header. Only the **admin** login calls Django's `login()`, which rotates the CSRF token, so
  the frontend re-fetches `/api/csrf/` right after an admin signs in. The member JWT login does not rotate it.
* **No IDOR by design:** members only have `/api/profiles/me/...`. No route takes a profile's id, and an
  emergency contact is looked up **inside the caller's own profile**, so someone else's contact id returns
  **404** (not 403), which does not reveal that it exists.
* **Request ids:** `core.middleware.RequestIdMiddleware` accepts an incoming `X-Request-ID` only if it is a
  valid UUID, otherwise generates one. It is returned on every response, included in error bodies and stored
  on every audit event, so one user action can be traced across all three.
* All errors share one shape: `{"error": {"code", "message", "fields", "request_id"}}`.

### Code layout

| App | Responsibility |
|---|---|
| `accounts` | custom `User`, signup, JWT login/refresh/logout, `CookieJWTAuthentication` |
| `profiles` | the four section tables, `services.py` (all write rules + completion), member API |
| `audit` | append-only `AuditEvent` model, `record_event()` (required) and `log_event()` (best-effort) |
| `adminpanel` | admin session login, `IsAdminRole`, allow-list serializers, filters, audit endpoints |
| `core` | request-id middleware, error handler, CSRF endpoint, `explain_queries` command |

Views stay thin: authenticate, validate with a serializer, then in **one** `transaction.atomic()` call **one**
function in `profiles/services.py` and write **one** required audit event. Every service function takes the
profile row lock and ends with `recalculate_completion()`, so the change, the stored completion and the audit
row commit together or not at all.

### Required vs best-effort audit events

| Kind | Events | If the audit insert fails | Why |
|---|---|---|---|
| **Required (fail closed)**: `record_event()` | `profile.created`, `profile.deleted`, `demographics.updated`, `wellness.updated`, `goals.updated`, `emergency_contact.created` / `.updated` / `.deleted`, `admin.profile_deactivated`, `admin.profile_reactivated` | The whole request rolls back (data **and** stored completion) and the API returns **503** `audit_unavailable` in the usual error shape. Nothing is saved, so the user can simply retry | These events record a **change to data**. A committed change with no audit row would be an unexplained gap in the history, so we refuse the change rather than lose the record |
| **Best-effort**: `log_event()` | `admin.login`, `admin.login_failed`, `admin.logout`, `admin.profile_viewed`, and every `outcome=denied` write attempt | A warning is logged and the request carries on | Nothing changed, so there is no un-audited change to protect. Failing closed here would only lock people out (or hide a "denied" answer behind a 503) when the audit table has a problem |

`record_event()` refuses to run outside a transaction, and `log_event()` writes inside its own savepoint so a failed
best-effort insert can never break a surrounding transaction. Failure-injection tests in
`tests/test_audit_durability.py` break the audit insert on purpose (including a real PostgreSQL rejection) and check
that every required write, **profile deletion included**, rolls back completely with no audit row.

## Architecture decisions

| Decision | Why | Trade-off |
|---|---|---|
| **Normalize into section tables** (demographics, contacts, wellness, goals) instead of one wide row | Each section has its own constraints, validation and lifecycle; goals become rows with a unique constraint instead of a JSON list | More tables and joins; a data migration was needed |
| **Store `completion_status` / `completion_percent`**, recalculated by one service function in the same transaction as every write | Admins can filter and sort by it cheaply; one writer keeps it correct | Denormalized duplicate of derivable data; protected by a single writer and tests |
| **Do not index `completion_status`** | Only 3 distinct values, so Postgres would rarely prefer the index over a scan | Filtering by completion scans the table; fine at this size, revisit if the table grows into the millions |
| **Append-only audit log**: model `save()`/`delete()` and queryset `update()`/`delete()` raise; no API route can change events | History must be trustworthy | A superuser with raw SQL could still edit rows. DB triggers or a separate write-only role would be stronger |
| **Audit stores field names only**; `log_event()` drops anything that is not a plain `snake_case` name | A value (phone, allergy text, search term) can never reach the log, even by mistake | Less detail: the log says *that* `phone` changed, not what it changed from or to |
| **`actor` is `SET_NULL` plus an `actor_role` snapshot** | History survives deleting an account and still says what kind of actor acted | A deleted actor shows as anonymous |
| **Contact events target the owning profile** (`target_type="health_profile"`) | One indexed lookup returns the whole history of a profile, including deleted contacts | The contact's own id is not in the log |
| **Admin responses use separate allow-list serializers** | A new column can never leak to admins by accident; masking is tested | Two serializer sets to maintain |
| **Max 3 contacts and "one primary" enforced in the service under a row lock**, with a partial unique index as backstop | Friendly 400 errors, race-safe, and the database refuses a violation even if code is bypassed | Rules live in two places (documented and tested) |
| **Phones stored in one canonical form**: optional `+` then **7–15 digits** (`"+92 (300) 123-4567"` → `"+923001234567"`), normalised by `profiles/phones.py` before validation, storage and the duplicate check; CHECK constraint `contact_phone_is_canonical` as backstop | Punctuation can no longer hide a non-number (`1------` is rejected) or a duplicate (`+92-300-123-4567` = `+92 300 1234567`), and the `(profile, phone)` unique constraint now catches equivalent formats too | No country rules without a new dependency: `0300 1234567` and `+92 300 1234567` (or `92…` and `+92…`) are still different numbers. Members see the compact canonical form |
| **Deactivated profile is read-only** (403 + a `denied` audit event) | Admins can freeze a profile without deleting data | Owner cannot fix their data until reactivated |
| **Drop Django's redundant single-column FK indexes** where a composite or unique index already starts with that column | Fewer indexes to maintain on writes; the justified index is the one Postgres uses | See "Lessons" below: Django also dropped a partial unique index by mistake, repaired in migration 0006 |
| **Admin login shares the member login throttle** (5/min per IP) | Same brute-force protection, no extra config | One shared budget per IP |

## Database

```mermaid
erDiagram
    USER ||--o| HEALTH_PROFILE : "owns (1 to 0..1)"
    HEALTH_PROFILE ||--o| DEMOGRAPHICS : "has"
    HEALTH_PROFILE ||--o{ EMERGENCY_CONTACT : "has up to 3"
    HEALTH_PROFILE ||--o| WELLNESS_PREFERENCE : "has"
    WELLNESS_PREFERENCE ||--o{ WELLNESS_GOAL : "has"
    USER ||--o{ AUDIT_EVENT : "actor (SET NULL)"
    USER ||--o{ OUTSTANDING_TOKEN : "issued JWT refresh"
    OUTSTANDING_TOKEN ||--o| BLACKLISTED_TOKEN : "revoked at logout"
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
        bigint user_id FK "unique, CASCADE"
        varchar status "active | deactivated"
        varchar completion_status "not_started | in_progress | complete"
        smallint completion_percent "CHECK 0..100"
        timestamptz created_at
        timestamptz updated_at
    }
    DEMOGRAPHICS {
        bigint id PK
        bigint profile_id FK "unique, CASCADE"
        varchar full_name
        varchar preferred_name
        date date_of_birth "nullable, SENSITIVE"
        varchar age_range "nullable; CHECK dob OR age_range"
        varchar gender
        varchar city
    }
    EMERGENCY_CONTACT {
        bigint id PK
        bigint profile_id FK "CASCADE"
        varchar name
        varchar relationship
        varchar phone "SENSITIVE; UNIQUE with profile"
        bool is_primary "UNIQUE per profile WHERE true"
    }
    WELLNESS_PREFERENCE {
        bigint id PK
        bigint profile_id FK "unique, CASCADE"
        varchar contact_preference
        varchar activity_level
        varchar diet_preference
        smallint sleep_goal_hours "CHECK 4..12"
        text allergies "SENSITIVE"
        text lifestyle_notes "SENSITIVE"
    }
    WELLNESS_GOAL {
        bigint id PK
        bigint preference_id FK "CASCADE"
        varchar goal "UNIQUE with preference"
    }
    AUDIT_EVENT {
        bigint id PK
        timestamptz created_at
        bigint actor_id FK "SET NULL"
        varchar actor_role "user | admin | anonymous"
        varchar action
        varchar target_type
        bigint target_id
        jsonb changed_fields "names only"
        uuid request_id
        varchar outcome "success | denied | failed"
    }
```

**Constraints** (all enforced by PostgreSQL, tested with `IntegrityError` tests): one profile per user; one
demographics / wellness row per profile; `UNIQUE (profile, phone)` so a number cannot be added twice; a
**partial unique index** so a profile has at most one primary contact; `UNIQUE (preference, goal)` so no
duplicate goals; `completion_percent` between 0 and 100; demographics need a date of birth **or** an age
range; sleep goal between 4 and 12; lower-case unique email; valid role / status values.

### Indexes (each one has a query that needs it)

| Index | Query it serves | Why |
|---|---|---|
| `profile_status_created_idx` on `(status, created_at DESC)` | Admin list filtered by status: `WHERE status = … ORDER BY created_at DESC` | Filters and sorts in one index scan |
| `audit_actor_created_idx` on `(actor, created_at DESC)` | Member activity page and the admin `?actor=` filter: `WHERE actor_id = … ORDER BY created_at DESC LIMIT 10` | "This person's recent activity, newest first" |
| `audit_target_created_idx` on `(target_type, target_id, created_at DESC)` | Admin profile history: `WHERE target_type = … AND target_id = … ORDER BY created_at DESC` | "The history of this profile, newest first" |
| unique `(profile, phone)`, unique `(preference, goal)`, partial unique `(profile) WHERE is_primary` | Constraints that also serve "all contacts of this profile" and "all goals of this preference" | The unique index already starts with the foreign-key column, so a separate FK index would be redundant (`db_index=False`) |
| unique `user_id`, unique `email` | `GET /profiles/me/`, login and signup lookups | Created by the constraints |

`completion_status` is deliberately **not** indexed (see decisions).

### Migrations

| Migration | What it does |
|---|---|
| `accounts/0001_initial` | custom `User` with email / role constraints (Week 1) |
| `profiles/0001_initial` | Week 1 single-table `HealthProfile` |
| `profiles/0002_week2_sections` | creates the 4 section tables and the completion columns (old columns still present) |
| `profiles/0003_copy_week1_data` | **data migration**: copies old rows into the new tables, maps old goal labels to goal codes (unknown labels are skipped), computes completion. Has a reverse function |
| `profiles/0004_remove_old_profile_columns` | drops the old columns and constraints |
| `profiles/0005_drop_redundant_fk_indexes` | removes automatic FK indexes that a composite / unique index already covers |
| `profiles/0006_restore_one_primary_contact_constraint` | **repair** for 0005 (see Lessons) |
| `profiles/0007_normalize_contact_phones` | **data**: rewrites stored phones into canonical form. Checks first and stops (changing nothing, naming contact ids only) if a row is not 7–15 digits or two contacts on one profile would become the same number |
| `profiles/0008_contact_phone_is_canonical` | adds the CHECK constraint `contact_phone_is_canonical` (one `ADD CONSTRAINT`, nothing dropped) |
| `audit/0001_initial`, `audit/0002_drop_redundant_fk_indexes` | the audit table with its two composite indexes |

`manage.py migrate` works on an empty database and on a Week 1 database (checked against the real Week 1 data
and by an automated test that migrates back to Week 1, inserts an old-style row and migrates forward).

**Lessons.** When migration 0005 removed the automatic index on `EmergencyContact.profile_id`, Django's schema
editor also dropped our partial unique index `contact_one_primary_per_profile`, because it sits on the same single
column. `makemigrations --check` could not notice (the model still declared it), but the "two primary contacts"
`IntegrityError` test failed, which is how it was found. Migration 0006 recreates it.

### EXPLAIN evidence

```bash
python manage.py seed_profiles --bulk 1000     # 1,000 members and about 5,000 audit events
python manage.py explain_queries               # prints the SQL and EXPLAIN (ANALYZE, BUFFERS)
```

Real output with 1,004 profiles (109 deactivated) and 5,037 audit events. The command runs `ANALYZE` first because
freshly loaded tables have no statistics yet.

**1) Admin list filtered by status**, using `profile_status_created_idx`:

```text
Sort  (cost=38.17..38.44 rows=109 width=51) (actual time=0.209..0.226 rows=109 loops=1)
  Sort Key: created_at DESC
  Sort Method: quicksort  Memory: 33kB
  Buffers: shared hit=17
  ->  Bitmap Heap Scan on profiles_healthprofile  (cost=9.12..34.48 rows=109 width=51) (actual time=0.051..0.121 rows=109 loops=1)
        Recheck Cond: ((status)::text = 'deactivated'::text)
        Heap Blocks: exact=13
        Buffers: shared hit=17
        ->  Bitmap Index Scan on profile_status_created_idx  (cost=0.00..9.09 rows=109 width=0) (actual time=0.027..0.029 rows=109 loops=1)
              Index Cond: ((status)::text = 'deactivated'::text)
              Buffers: shared hit=4
Planning Time: 0.196 ms
Execution Time: 0.266 ms
```

For the **common** value `status='active'` (about 89% of rows) Postgres correctly prefers a sequential scan plus
sort, because reading almost the whole table is cheaper than walking the index. The index pays off for selective
values such as `deactivated`.

**2) A member's activity page** (`WHERE actor_id = 5 ORDER BY created_at DESC, id DESC LIMIT 10`), using
`audit_actor_created_idx`:

```text
Limit  (cost=2.82..23.44 rows=9 width=118) (actual time=0.032..0.034 rows=9 loops=1)
  Buffers: shared hit=7
  ->  Incremental Sort  (cost=2.82..23.44 rows=9 width=118) (actual time=0.032..0.032 rows=9 loops=1)
        Sort Key: created_at DESC, id DESC
        Presorted Key: created_at
        Full-sort Groups: 1  Sort Method: quicksort  Average Memory: 26kB  Peak Memory: 26kB
        Buffers: shared hit=7
        ->  Index Scan using audit_actor_created_idx on audit_auditevent  (cost=0.28..23.03 rows=9 width=118) (actual time=0.020..0.024 rows=9 loops=1)
              Index Cond: (actor_id = 5)
              Buffers: shared hit=7
Planning Time: 0.150 ms
Execution Time: 0.052 ms
```

**3) History of one profile** (`WHERE target_type = 'health_profile' AND target_id = 1040 …`), using
`audit_target_created_idx`:

```text
Limit  (cost=2.85..21.09 rows=8 width=118) (actual time=0.063..0.064 rows=8 loops=1)
  Buffers: shared hit=5
  ->  Incremental Sort  (cost=2.85..21.09 rows=8 width=118) (actual time=0.062..0.063 rows=8 loops=1)
        Sort Key: created_at DESC, id DESC
        Presorted Key: created_at
        Full-sort Groups: 1  Sort Method: quicksort  Average Memory: 26kB  Peak Memory: 26kB
        Buffers: shared hit=5
        ->  Index Scan using audit_target_created_idx on audit_auditevent  (cost=0.28..20.73 rows=8 width=118) (actual time=0.050..0.054 rows=8 loops=1)
              Index Cond: (((target_type)::text = 'health_profile'::text) AND (target_id = 1040))
              Buffers: shared hit=5
Planning Time: 0.129 ms
Execution Time: 0.082 ms
```

The *Incremental Sort* appears because the query also orders by `id` (a tie-breaker so pages never repeat a row).
The index already delivers rows in `created_at` order; only ties need a tiny extra sort.

**An honest finding.** The first time this was run, query 2 used Django's automatic single-column index on
`actor_id` instead of `audit_actor_created_idx`, because both existed. That automatic index was redundant (the
composite index starts with `actor`), so it was dropped in `audit/0002`, and Postgres now uses the justified one.

## Features

* Sign up (name, email, password strength meter), sign in, sign out
* **Sectioned profile page:** demographics, emergency contacts (add / edit / make primary / delete, max 3),
  wellness preferences and goals, each section saved on its own, with a completion progress card
* **Delete my profile** with typed confirmation (your account stays)
* **My activity** page: your own audit trail, newest first
* Deactivated profiles are read-only for their owner
* **Admin portal:** search, status / completion / date filters, ordering, completion column, detail panel,
  full profile page (masked), profile history, deactivate / reactivate with confirmation, **Audit log** page with filters
* Light and dark themes (system setting + toggle); responsive single column on mobile; labelled form fields

## Run it locally

**Prerequisites:** Python **3.12 or newer**, PostgreSQL, Node 20+.

> Django 6 (pinned in `requirements.txt`) does not support older Python versions. On Python 3.11 or below,
> `pip install -r requirements.txt` fails because no matching Django version can be installed. Check yours with
> `python --version`.

Start the **backend first, then the frontend**. The frontend forwards its `/api/*` calls to the backend, so
sign-in, sign-up and every page that loads data fail until the backend is running.

Each block below says which shell it is for. Run the steps in order.

### 1. Create the PostgreSQL database and login

Do this once. Pick your own password and keep it to yourself; never commit it.

In **pgAdmin**: connect to your server, then open *Query Tool* on the `postgres` database and run the SQL below.
Or from a terminal with `psql -U postgres`.

```sql
CREATE USER healthprofile_user WITH PASSWORD 'choose-your-own-password';
CREATE DATABASE healthprofile OWNER healthprofile_user;
```

On PostgreSQL 15 or newer, also give the user rights on the public schema (connect to the `healthprofile`
database first; in `psql` use `\c healthprofile`):

```sql
GRANT ALL ON SCHEMA public TO healthprofile_user;
```

Your `DATABASE_URL` (step 3) will then be
`postgres://healthprofile_user:<your-password>@localhost:5432/healthprofile`.

### 2. Backend: virtualenv and dependencies

**Windows PowerShell** (from the project root):

```powershell
cd backend
py -3.12 -m venv venv                 # or: python -m venv venv  (must be Python 3.12+)
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell refuses to run the activate script, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.

**Windows cmd** (from the project root):

```bat
cd backend
py -3.12 -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

**macOS / Linux** (bash or zsh, from the project root):

```bash
cd backend
python3 -m venv venv                  # python3 must be 3.12+
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Backend: configure `.env`

You are already inside `backend/`. Copy the example file and fill it in.

* PowerShell: `Copy-Item .env.example .env`
* cmd: `copy .env.example .env`
* macOS / Linux: `cp .env.example .env`

Then edit `backend/.env`:

* `DATABASE_URL`: the connection string from step 1.
* `SECRET_KEY` and `JWT_SIGNING_KEY`: generate **two separate** random values, one for each. They must differ
  from each other and from any example value. Run this command twice (it works in every shell, with the venv active):

  ```
  python -c "import secrets; print(secrets.token_urlsafe(64))"
  ```

  Paste the first output as `SECRET_KEY` and the second as `JWT_SIGNING_KEY`.
* `DEBUG=True` for local development.

Never commit `backend/.env`; it is git-ignored.

### 4. Backend: migrate, seed and start (same commands in every shell)

Still in `backend/` with the venv active:

```
python manage.py migrate
python manage.py seed_profiles        # 5 demo members, password: CalmMorning2026
python manage.py create_admin --email admin@healthprofile.test --name "Clinic Admin"
python manage.py runserver            # http://127.0.0.1:8000  (Swagger: /api/docs/)
```

`create_admin` asks for the admin password (input is hidden). Choose your own; there is no default admin password.
Leave this terminal running.

### 5. Frontend (open a second terminal)

From the project root, in any shell:

```
cd frontend
npm install
npm run dev                           # http://localhost:3000
```

Open http://localhost:3000. Members sign in at `/login`, admins at `/admin/login`.

### Verified from a clean clone

Checked on a fresh clone with a new, empty database:

* `python manage.py migrate` succeeded.
* `seed_profiles` and `create_admin` ran.
* `python -m pytest` gave **223 passed** (with 192 warnings).
* A member and an admin could both sign in on the fresh copy.

The 5 demo members: `momina.asif` (complete), `bilal.ahmed` and `sara.noor` (in progress), `zainab.iqbal`
(not started), `hamza.malik` (complete but deactivated), all `@example.com`.

Pages: `/signup`, `/login`, `/profile`, `/activity`, `/admin/login`, `/admin`, `/admin/profiles/[id]`, `/admin/audit`.

Other commands:

```bash
python manage.py seed_profiles --bulk 1000   # extra members + audit events for the EXPLAIN demo
python manage.py explain_queries             # real query plans for the indexed lookups
python manage.py makemigrations --check      # confirms no migration is missing
npm test && npm run lint && npm run build    # in frontend/
```

## Environment configuration

Real secrets live only in `backend/.env`, which is **git-ignored** and never committed. The committed
`backend/.env.example` and `frontend/.env.example` contain placeholders only; copy them and fill in your own values.

| File | Variable | What it does |
|---|---|---|
| `backend/.env` | `DEBUG` | `True` for local development. When `False`, cookies are marked `Secure` (HTTPS only). Defaults to `False` if unset. |
| `backend/.env` | `SECRET_KEY` | Django's secret key (sessions, CSRF). Use a long random value. |
| `backend/.env` | `JWT_SIGNING_KEY` | Key that signs the member JWTs. Keep it different from `SECRET_KEY`. |
| `backend/.env` | `DATABASE_URL` | PostgreSQL connection string, e.g. `postgres://user:password@localhost:5432/healthprofile`. |
| `backend/.env` | `ALLOWED_HOSTS` | Comma-separated hostnames Django will serve. Defaults to `localhost,127.0.0.1`. |
| `backend/.env` | `CSRF_TRUSTED_ORIGINS` | Comma-separated origins allowed to send CSRF-protected requests (the Next.js frontend). Defaults to `http://localhost:3000,http://127.0.0.1:3000`. |
| `frontend/.env` | `BACKEND_URL` | Where Next.js forwards `/api/*` calls. Defaults to `http://127.0.0.1:8000`. |

## Tests

```bash
cd backend
python -m pytest        # 262 passed
```

| File | What it proves |
|---|---|
| `test_models_week2.py` | every `IntegrityError` constraint, completion rules (0% / 25% / 100% / back to 75%), and the Week 1 → Week 2 data migration |
| `test_profiles.py` | 401 on every member route, own-data-only, 409 on a second profile, profile `DELETE`, deactivated profile = read-only (403 + audited), CSRF required on every write |
| `test_profile_sections.py` | demographics and wellness: PUT replace vs PATCH, validation (future / ancient date of birth, bad choices, ranges), goals replaced atomically |
| `test_emergency_contacts.py` | CRUD, max 3, primary rule, duplicate phone, **member A cannot read, edit or delete member B's contact (404)** |
| `test_phone_normalisation.py` | punctuation-heavy input (`1------`), the 7 / 15 digit boundaries, canonical storage, equivalent formats as duplicates on POST and PATCH, the fourth-contact limit in any format, the database CHECK, and migration 0007 (rewrites rows; stops on unsafe rows naming ids only) |
| `test_audit.py` | exactly one event per write, no secrets or values in any audit field, append-only, request id on every response and in the audit row, member activity |
| `test_audit_durability.py` | failure injection: when the required audit insert fails, every member write, profile deletion and admin deactivate / reactivate returns 503 `audit_unavailable` and rolls back completely (data, stored completion, no audit row) |
| `test_admin.py`, `test_admin_week2.py` | admin session list / search / detail, every filter and ordering, invalid values → 400, deactivate / reactivate with CSRF, login throttle, audit endpoints, **a member JWT gets 403 on every admin route and an admin session cannot use member routes** |
| `test_sensitive_fields.py` | admin responses lack date of birth, allergies, lifestyle notes and full phones; no response anywhere contains password, token or session data |
| `test_jwt.py`, `test_signup.py` | Week 1 auth: expiry, tampering, blacklisting, hashing, role injection ignored |

```bash
cd frontend
npm test                # 11 passed (Vitest + Testing Library, jsdom)
```

| File | What it proves |
|---|---|
| `tests/ConfirmDialog.test.tsx` | the confirm dialog's keyboard behaviour: focus starts on Cancel (or on the type-to-confirm box), Tab / Shift+Tab stay inside, Escape closes but not while busy (focus then stays on the dialog box), focus returns to the opener, or to a fallback when the opener is gone or disabled |
| `tests/admin-page.test.tsx` | where focus lands on the admin page after a deactivate or reactivate: the selected profile's heading if it is still listed, otherwise the "Member profiles" heading (e.g. when the Active filter loses its last match) |
| `tests/contacts-card.test.tsx` | after deleting an emergency contact and reloading the list, focus lands on the "Emergency contacts" heading, not on the page body |
| `tests/profile-page.test.tsx` | after deleting the whole profile, focus lands on the "Create your wellness profile" heading, not on the page body |

## API

Full interactive docs: **http://127.0.0.1:8000/api/docs/** (Swagger, grouped by *member profile*, *admin profiles*,
*admin audit*, *admin auth*, with request examples). "CSRF" means the `X-CSRFToken` header is required.

### Member endpoints (JWT cookie; all scoped to the signed-in member)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/csrf/` | none | Sets the `csrftoken` cookie |
| POST | `/api/auth/signup/` | none | Register → 201 / 400 / 409 |
| POST | `/api/auth/user/login/` | CSRF (throttled 5/min) | Sets `access` + `refresh` cookies |
| POST | `/api/auth/user/refresh/` | refresh cookie + CSRF | Rotates tokens |
| POST | `/api/auth/user/logout/` | cookie + CSRF | Blacklists refresh, clears cookies |
| GET | `/api/auth/me/` | JWT | Current user |
| GET | `/api/profiles/me/` | JWT | Whole profile: sections + completion (404 if none) |
| POST | `/api/profiles/me/` | JWT + CSRF | Create the empty root profile (409 if it exists) |
| DELETE | `/api/profiles/me/` | JWT + CSRF | Delete the profile and all sections (204); the account stays |
| GET / PUT / PATCH | `/api/profiles/me/demographics/` | JWT (+ CSRF on writes) | Read / create-or-replace / partial update |
| GET / PUT / PATCH | `/api/profiles/me/wellness/` | JWT (+ CSRF on writes) | Preferences + goals (goals replaced atomically) |
| GET / POST | `/api/profiles/me/emergency-contacts/` | JWT (+ CSRF on POST) | List / add (max 3, else 400) |
| GET / PATCH / DELETE | `/api/profiles/me/emergency-contacts/{id}/` | JWT (+ CSRF on writes) | One contact, looked up only inside my profile (else 404) |
| GET | `/api/profiles/me/activity/` | JWT | My own audit events, newest first, paginated |

A deactivated profile can be read (200) but every write and `DELETE` returns 403.

### Admin endpoints (server session; a member JWT gets 403)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/admin/login/` | CSRF, throttled 5/min | Start a session (403 for non-admins); audited |
| POST | `/api/admin/logout/` | session + CSRF | End the session on the server; audited |
| GET | `/api/admin/me/` | session | Current admin |
| GET | `/api/admin/profiles/` | session + admin | List. Filters: `search`, `status`, `completion_status`, `created_after`, `created_before`, `ordering`, `page` |
| GET | `/api/admin/profiles/{id}/` | session + admin | Detail (sensitive fields hidden, phones masked); audited as `admin.profile_viewed` |
| POST | `/api/admin/profiles/{id}/deactivate/` | session + admin + CSRF | Deactivate; audited |
| POST | `/api/admin/profiles/{id}/reactivate/` | session + admin + CSRF | Reactivate; audited |
| GET | `/api/admin/profiles/{id}/audit-events/` | session + admin | History of one profile |
| GET | `/api/admin/audit-events/` | session + admin | All events, read-only. Filters: `action`, `actor`, `outcome`, `created_after`, `created_before` |

`ordering` accepts `created_at`, `-created_at`, `completion_percent`, `-completion_percent`; anything else is a 400.

Status codes: 400 invalid input, 401 not signed in / token expired, 403 not allowed (including missing CSRF,
a deactivated profile, or a member on an admin route), 404 not found, 409 duplicate email or profile,
429 login throttled.

### Sample requests and responses (real output)

Member: read my whole profile (`GET /api/profiles/me/`, abridged):

```json
{
  "id": 1040,
  "status": "active",
  "completion": { "status": "complete", "percent": 100, "missing": [] },
  "demographics": { "full_name": "Momina Asif", "age_range": "25-34", "gender": "female", "city": "Karachi", "…": "…" },
  "emergency_contacts": [
    { "id": 6, "name": "Bilal Ahmed", "relationship": "sibling", "phone": "+92 300 0000001", "is_primary": true }
  ],
  "wellness": {
    "contact_preference": "sms", "activity_level": "moderate", "sleep_goal_hours": 8,
    "allergies": "Peanuts", "goals": ["better_sleep", "more_activity"]
  }
}
```

Member: validation error (`PUT /api/profiles/me/demographics/` with `{"full_name": "Momina Asif", "date_of_birth": "2999-01-01"}`):

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid input.",
    "fields": { "date_of_birth": ["Date of birth cannot be in the future."] },
    "request_id": "453e9b73-5601-41fb-aac8-d268288d351e"
  }
}
```

Member: a 4th emergency contact (`POST /api/profiles/me/emergency-contacts/`) → **400**:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid input.",
    "fields": { "emergency_contacts": ["You can save at most 3 emergency contacts."] },
    "request_id": "c64d5e53-05ad-4af3-93d6-c27d83a48cae"
  }
}
```

Member: my activity (`GET /api/profiles/me/activity/`): field **names** only, never values:

```json
{
  "count": 9, "next": null, "previous": null,
  "results": [
    {
      "id": 5041, "created_at": "2026-10-20T18:29:17.694228+05:00",
      "action": "emergency_contact.deleted", "target_type": "health_profile", "target_id": 1040,
      "changed_fields": [], "outcome": "success",
      "request_id": "cf19e3d4-8635-485c-b79c-25722d2b6eeb"
    }
  ]
}
```

Admin: the same profile (`GET /api/admin/profiles/1040/`). Note what is **missing**: date of birth, allergies,
lifestyle notes, the full phone number.

```json
{
  "id": 1040, "display_name": "Momina", "email": "momina.asif@example.com",
  "status": "active", "completion_status": "complete", "completion_percent": 100,
  "demographics": { "full_name": "Momina Asif", "preferred_name": "Momina", "age_range": "25-34", "gender": "female", "city": "Karachi" },
  "emergency_contacts": [
    { "id": 6, "name": "Bilal Ahmed", "relationship": "sibling", "phone_masked": "•••• •••• 0001", "is_primary": true }
  ],
  "wellness": {
    "contact_preference": "sms", "activity_level": "moderate", "diet_preference": "no_preference",
    "sleep_goal_hours": 8, "goals": ["better_sleep", "more_activity"], "has_allergies": true
  }
}
```

Admin: list row (`GET /api/admin/profiles/?search=momina.asif@&completion_status=complete&ordering=-completion_percent`):
only 7 fields.

```json
{ "id": 1040, "display_name": "Momina", "email": "momina.asif@example.com", "status": "active",
  "completion_status": "complete", "completion_percent": 100, "created_at": "2026-10-18T18:15:39.480747+05:00" }
```

Admin: invalid ordering (`?ordering=email`) → **400**:

```json
{ "error": { "code": "validation_error", "message": "Invalid input.",
             "fields": { "ordering": ["\"email\" is not a valid choice."] },
             "request_id": "95176f1a-cbae-497e-ad5d-b72d373189ba" } }
```

Admin: an audit event (`GET /api/admin/profiles/1040/audit-events/`). The actor is an id only, never an email:

```json
{ "id": 5043, "created_at": "2026-10-20T18:29:19.119259+05:00", "actor": 6, "actor_role": "admin",
  "action": "admin.profile_viewed", "target_type": "health_profile", "target_id": 1040,
  "changed_fields": [], "outcome": "success", "request_id": "cd5c9552-ed9f-437a-9066-fbbbbb688cff" }
```

Week 1 example (still valid): `POST /api/auth/user/login/` with `{ "email": "momina.asif@example.com", "password": "CalmMorning2026" }`
→ `200` and two `HttpOnly; SameSite=Lax` cookies (`access`, `refresh`), no token in the body.

## Screenshots

### Week 1

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

### Week 2 (capture these into `docs/screenshots/week2/`)

| File | What to show |
|---|---|
| `profile-sections.png` | Member `/profile` (sign in as `momina.asif@example.com`): the three sections and the **completion card at 100%** |
| `profile-contacts.png` | Emergency contacts card with the **Primary** badge and the disabled "Add contact" button at 3 contacts |
| `delete-dialog.png` | "Delete your profile?" dialog with the `DELETE` typed-confirmation box |
| `profile-readonly.png` | Sign in as `hamza.malik@example.com`: the "deactivated" banner and read-only form |
| `activity.png` | `/activity`: the member's own change history (field names only) |
| `admin-filters.png` | `/admin` with the filters row, the **Completion** column and a sort applied |
| `admin-detail-masked.png` | `/admin/profiles/{id}`: masked phone (`•••• •••• 0001`), "Allergies: Recorded (private)", profile history |
| `admin-audit.png` | `/admin/audit` with a filter applied |
| `swagger-week2.png` | `/api/docs/` showing the *member profile*, *admin profiles* and *admin audit* groups |
| `explain.png` | Terminal: `python manage.py explain_queries` after `seed_profiles --bulk 1000` |
| `pytest-week2.png` | Terminal: `python -m pytest` → **224 passed** |

## AI workflow

How AI was used to plan, build, review and debug this project, including prompt iterations, blast radius
control, a manual security review and a bug story: see [docs/ai-workflow.md](docs/ai-workflow.md).
The rules the AI must follow in this repo are in [CLAUDE.md](CLAUDE.md).

## Demo video

Week 1: https://www.loom.com/share/7f3a96d221f1415b9c2abe2070b3f38e

Week 2: https://www.loom.com/share/5d16ef5c30ba4496a1de8ce16270edba

## Limitations

* Intended for local development: set `DEBUG=False` and HTTPS for production (cookies then become `Secure`).
* The audit log is append-only **in the application** (ORM guards and no API route). A database superuser with raw
  SQL could still edit rows; database triggers or a write-only role would be the next hardening step.
* Admin login shares the member login throttle (5 per minute per IP), so the two portals share one attempt budget.
* The "Renews in N min" label is an estimate from when the page last saw a login or refresh, because the token
  cookies are HttpOnly and cannot be read by JavaScript.
* Pagination `next` links are absolute URLs that show the backend host (`127.0.0.1:8000`); the frontend only
  checks that the link exists, so it is cosmetic.
* The data migration `0003` can be reversed, but reversing `0004` on a table that already has rows needs a default
  for the old required `full_name` column (the Week 1 column had none).
* The admin `created_after` / `created_before` filters use the server time zone (Asia/Karachi).
* No password reset, email verification, or admin-created members yet. Wellness goals are personal goals only,
  never medical advice.
