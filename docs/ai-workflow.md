# AI-Assisted Development Workflow

> How I used AI to plan, build, review and debug HealthProfile, and how I checked its work.

## 1. Tools I used and why

Apart from installing the tools and taking the screenshots, I used AI for every part of this project.

| Tool | What I used it for |
|---|---|
| **Claude (chat)** | Understanding the brief; planning the architecture, database and endpoints (a written build plan); choosing and mocking up the UI theme (Calm Clinic light + Midnight dark); step-by-step guidance for setup and the first backend pieces (custom User model, signup, JWT login / refresh / logout / me); debugging; reviewing Claude Code's output; writing the structured prompt I gave to Claude Code |
| **Claude Code** (AI coding agent in my repo) | Generating the rest of the project: the HealthProfile model and `/profiles/me/` API, the admin session portal, the `create_admin` and `seed_profiles` commands, the 51-test suite, the Next.js frontend with light/dark themes, README and docs updates, and packaging the project as a zip |
| **Swagger UI** (`/api/docs/`) | Manually testing endpoints and checking real status codes |
| **Browser DevTools** | Checking that `access` and `sessionid` cookies are `HttpOnly` and `SameSite=Lax` |

## 2. Context management

- I did the long discussion once, in Claude chat: requirements, the build plan, the UI theme and the first backend steps. I did not repeat it in every new prompt.
- To hand that context to Claude Code I first tried sharing the chat links (see §3). When that failed, I condensed the context into **one structured prompt** plus **images of the finalized UI theme**. That was far shorter than the chats and gave Claude Code only what it needed.
- The prompt split the work into **phases** with an explicit list of files per phase, so the agent never needed the whole conversation history.

## 3. Prompt iterations

### Starting point: the brief, in Claude chat

My first prompt was the **Week 1 assignment PDF** plus my **mentor's clarification message** (which listed every requirement to be fulfilled), pasted into Claude chat with a request to help me build it. From there Claude explained the requirements in simple terms, helped me write a build plan, design the UI theme, and guided me step by step through setup and the first backend features.

### Claude Code iterations 1 and 2: share the chat links

My first two attempts were to give Claude Code the links to my long Claude chats (from tool setup to the final interface theme) and ask it to continue the project from there, so I wouldn't have to retype or copy everything.

**Result:** both attempts failed. Claude Code could not read the shared chats, so it had no reliable context about my requirements, auth design or theme.

### Claude Code iteration 3: structured prompt + design images

I then used the prompt structure taught in our AI Vibe Coding session. I asked Claude to write the prompt in that structure, and gave it to Claude Code together with screenshots of the finalized interface theme. I changed `CURRENT PHASE` for each phase of the build. The full prompt:

```text
ROLE
You are a senior full-stack engineer working in this repository (Django + DRF backend, Next.js frontend). You write secure, minimal, well-tested code and explain your decisions. Never guess silently: if something is unclear, choose the safest option and list it under Unknowns.

GOAL
Complete the CURRENT PHASE of "HealthProfile" so every acceptance item for that phase is demonstrably met and `pytest` passes with zero failures.
Overall project: a role-based HealthTech profile builder where self-registered users authenticate with JWT and database-provisioned admins authenticate with server-side sessions. Synthetic data only.

CURRENT PHASE: 1        <- I change this number each session

CONTEXT
- Source of truth: docs/PLAN.md (architecture, tables, endpoints, tests). Read it first. If this prompt conflicts with it, ask me.
- Layout: backend/{config, accounts, profiles, adminpanel, core, tests}, frontend/ (Next.js App Router, TypeScript), docs/.
- Stack: Python 3.12+, Django, DRF, djangorestframework-simplejwt (+ token_blacklist), PostgreSQL 17 via psycopg, django-environ, drf-spectacular, pytest + pytest-django + freezegun, Faker. Next.js reaches the API only through a rewrite /api/* -> Django (same origin, no CORS package).
- User auth: signup with name, email, password. Login sets JWTs in HttpOnly, SameSite=Lax cookies (Secure when DEBUG=False): access 15 min, refresh 1 day scoped to /api/auth/user/, rotation + blacklist on. No tokens in the response body or localStorage. Claims: user_id, exp, jti, token_type only. A custom CookieJWTAuthentication reads the cookie and enforces CSRF on unsafe methods.
- Admin auth: role=admin accounts are created ONLY by `python manage.py create_admin` (password from interactive prompt or env var, never hardcoded). POST /api/admin/login/ uses Django sessions (sessionid HttpOnly, 30-min idle expiry, SESSION_SAVE_EVERY_REQUEST=True). CSRF required on state-changing admin requests. Logout deletes the server-side session.
- Separation rule: every view sets authentication_classes and permission_classes explicitly. User views: CookieJWTAuthentication only. Admin views: SessionAuthentication + IsAdminRole (role read from the database). A user JWT must get 403 on every admin route. Frontend state is never trusted.
- Data model:
  - User: custom, email login; email lowercased on save + UniqueConstraint(Lower('email')); name; role (user|admin) with CheckConstraint; is_active; timestamps.
  - HealthProfile: OneToOne -> User, on_delete=CASCADE. Fields: full_name, date_of_birth (nullable, not in future), age_range (nullable; CheckConstraint requires dob OR age_range), contact_preference (email|phone|sms), wellness_goals, allergies (optional), emergency_contact_name + emergency_contact_phone (fictional), lifestyle_notes (optional), status (active|deactivated), created_at, updated_at.
  - Indexes: composite (status, -created_at) for the admin list query. Optional GIN trigram on full_name ONLY if I ask for the search demo. No other index without a query that uses it.
- Endpoints (exact list in docs/PLAN.md): /api/csrf/; /api/auth/signup/, user/login/, user/refresh/, user/logout/, me/; /api/profiles/me/ (POST, GET, PATCH); /api/admin/login/, logout/, me/, profiles/ (list + ?search= + ?status= + pagination), profiles/{id}/, profiles/{id}/deactivate/; /api/docs/ (Swagger). Users get NO /profiles/{id} route.
- Errors: one JSON shape from a custom DRF exception handler: {"error": {"code", "message", "fields"}}. Status codes 400 / 401 / 403 / 404 / 409.
- Domain: wellness only. No diagnoses, clinical advice or real patient data. All seed data generated by Faker and clearly synthetic.

PHASES
1. Foundation + user auth: project + settings from .env, .env.example, .gitignore, custom User + its migration (before ANY other migration), signup, user login/refresh/logout/me with cookie JWT, /api/csrf/, exception handler, password validators, login throttling, tests.
2. Profiles: HealthProfile model, constraints, index, migration; /profiles/me/ POST/GET/PATCH with validation + ownership; `seed_profiles` command (>=5 demo users, plus `--bulk N` for the EXPLAIN demo); tests.
3. Admin: `create_admin` command; session login/logout/me; IsAdminRole; admin list/search/paginate/detail/deactivate; drf-spectacular Swagger; tests.
4. Frontend: next.config.js rewrite; lib/api.ts (credentials included, X-CSRFToken header, on 401 refresh once -> retry -> redirect to login); pages /signup, /login, /profile, /admin/login, /admin, /admin/profiles/[id]; responsive; client validation mirrors backend rules; clear error messages.
5. Proof + docs: `explain_admin_query` command printing the EXPLAIN ANALYZE plan; README (problem, architecture, stack, env setup, how to run, features, API examples with auth requirement, limitations, screenshots); Mermaid ER diagram.

IN SCOPE (current phase only, plus its tests and NEW migrations)
- Phase 1: backend/config/, backend/accounts/, backend/core/, backend/tests/test_signup.py, backend/tests/test_jwt.py, backend/requirements.txt, backend/.env.example, .gitignore
- Phase 2: backend/profiles/, backend/tests/test_profiles.py
- Phase 3: backend/adminpanel/, backend/tests/test_admin.py, backend/config/urls.py, backend/config/settings.py (spectacular + session settings only)
- Phase 4: frontend/
- Phase 5: README.md, backend/core/management/commands/explain_admin_query.py

OUT OF SCOPE (do not touch)
- Any file outside the current phase's list. If a change elsewhere seems necessary, STOP and explain why instead of making it.
- Already-applied migrations (create new ones only), docs/PLAN.md, docs/ai-workflow.md.
- New dependencies beyond CONTEXT (ask first).
- Public admin signup; accepting `role` from any request body; tokens in localStorage or response bodies; Django's built-in /admin/ site; CORS packages; ML features; real or identifiable patient data; committing .env or any secret.
- Refactoring or "improving" working code the phase doesn't require.

ACCEPTANCE (whole project; meet the subset for the current phase)
- Signup: 201 when valid; 400 with field errors for bad email, weak password, missing fields; 409 for duplicate email in any letter case; a `role` sent in the body is ignored.
- User JWT: login sets HttpOnly cookies and returns no token in the body; wrong password or inactive user -> 401; expired token (freezegun), tampered token, and refresh after logout (blacklisted) -> 401; logout clears both cookies.
- Profiles: no cookie -> 401; second POST -> 409; GET before creating -> 404; PATCH of one field leaves the others unchanged and moves updated_at; future date of birth or invalid choice -> 400; owner editing a deactivated profile -> 403.
- Admin: create_admin makes role=admin with a hashed password; non-admin credentials at admin login -> 403; user JWT on any /api/admin/* -> 403; admin session list/search/detail -> 200 and paginated; deactivate without CSRF -> 403, with CSRF -> 200; old sessionid after logout -> 403 and its session row is gone.
- Database: migrations apply cleanly on an empty PostgreSQL database; constraint violations raise IntegrityError (tested); with >=1000 seeded rows, EXPLAIN of filter(status='active').order_by('-created_at') shows the composite index in use.
- Security: secrets only from env; Secure cookies when DEBUG=False; login throttled; `python manage.py check --deploy` warnings reviewed and listed.
- `pytest` passes with zero failures.

PROCESS: Inspect -> plan -> implement -> validate
1. Inspect: read docs/PLAN.md and the in-scope files. Summarise the current state in at most 10 lines.
2. Plan: list each file you will create or modify and why, and each test you will add. Then STOP and wait for me to reply "go".
3. Implement: the smallest change that meets acceptance. Follow existing patterns. Comment only where intent isn't obvious. No placeholder TODOs in logic.
4. Validate: run migrations and `pytest` (if you can't run commands, give me the exact commands). Fix failures and re-run.

OUTPUT
- Changed files: path + one-line purpose, and confirm no file outside scope was touched.
- Commands run and test results (passed/failed counts).
- Risks: security or correctness concerns, and what I should review by hand.
- Unknowns: assumptions you made and questions for me.
- A suggested commit message.
```

**How the result differed from what the prompt expected:**

- `docs/PLAN.md` lived in a Claude chat document rather than in the repo, so the plan was carried by this prompt itself.
- The prompt expected the `(status, created_at)` index to be used for `status='active'`. The real EXPLAIN plan showed Postgres prefers a sequential scan when about 89% of rows are active; the index is used for selective filters such as `status='deactivated'` (see README).
- The `explain_admin_query` command was not needed: the README shows the EXPLAIN command and its real output instead.

### What changed between the iterations

| | Iterations 1–2 (chat links) | Iteration 3 (structured prompt) |
|---|---|---|
| Context | Agent could not read it | Everything needed, in one structured prompt |
| Auth design | Unknown to the agent | User JWT and admin session explicitly separated |
| UI | No reference | Matched the finalized theme from the images |
| Scope | Undefined | Per-phase file lists + OUT OF SCOPE rules |
| Verification | None | Acceptance list + required tests |

## 4. Controlling the blast radius

- Each phase in the prompt listed the **only** files the agent could change, plus an explicit OUT OF SCOPE list (no new dependencies, no edits to applied migrations, no tokens in `localStorage`, no public admin signup).
- The agent had to **show a plan and stop** before implementing.
- Work stayed on feature branches (`feature/phase1-user-auth`, then `feature/phase2-profiles-admin-frontend`) with commits grouped by area (profiles/admin/frontend, docs, cleanup) and is merged to `main` through a pull request.
- After the agent's changes I verified behaviour myself instead of trusting its summary: `python -m pytest`, `npm run lint`, `npm run build`, and a manual click-through of every page (see §7).
- For the final polish I gave Claude Code a second scoped prompt that only allowed doc/config changes and explicitly forbade touching models, views, tests or frontend source.

## 5. Manual security review of the AI's code

| Check | Where | Result |
|---|---|---|
| Passwords stored only as hashes | `accounts/models.py` (`set_password`); test `test_valid_signup_creates_user_with_hashed_password` | ✅ |
| Signup can't create admins (`role`, `is_staff` ignored) | `SignupSerializer` accepts only 3 fields; test `test_role_in_body_is_ignored` | ✅ |
| JWT holds no secrets (only `user_id`, `exp`, `jti`, `token_type`) | `RefreshToken.for_user` | ✅ |
| Tokens in HttpOnly cookies, not the response body | `accounts/cookies.py`; DevTools screenshot | ✅ |
| User views accept only JWT; admin views only session + `IsAdminRole` | explicit `authentication_classes` on every view; `DEFAULT_AUTHENTICATION_CLASSES = []` | ✅ |
| Role always read from the database | `IsAdminRole`, `CookieJWTAuthentication` | ✅ |
| No IDOR: users have no `/profiles/{id}/` route | `profiles/urls.py`; test `test_user_only_sees_own_profile_and_no_route_to_others` | ✅ |
| CSRF on every state-changing cookie request | `enforce_csrf`, `SessionAuthentication`; CSRF tests | ✅ |
| Secrets only in `.env`; `.env` git-ignored; `.env.example` committed | `.gitignore` | ✅ |
| Login brute-force throttled (5/min) | `ScopedRateThrottle`; test `test_login_is_throttled_after_five_attempts` | ✅ |

**Things I corrected after reviewing the AI's output** (with a second review in Claude chat):
- The README claimed Django rotates the CSRF token at *every* login. Only the admin (session) login does; the user JWT login does not. Corrected.
- The `(status, created_at)` index was described as serving the whole admin list. The EXPLAIN plan showed it is only used for selective filters, so I documented that honestly (§7, README).
- My real personal account was in the dev database. I removed it so screenshots and demos show synthetic data only.
- Leftover boilerplate (default Next.js README, unused SVGs, empty test files) was deleted.

## 6. Bug story: an unexpected AI-generated change

**Symptom.** `POST /api/auth/user/logout/` returned **403 "CSRF failed"** in Swagger, even after I pasted a fresh CSRF token.

**How I isolated it.**
1. `GET /api/auth/me/` worked, so the JWT cookie was fine. Only POST failed.
2. In Swagger's **Curl** box I saw an `X-CSRFTOKEN` header I had not typed: Swagger (drf-spectacular) adds it automatically from the `csrftoken` cookie.
3. The AI-generated view had **also** declared a manual `X-CSRFToken` header parameter. I filled that in too, so the header was sent **twice**; the values were merged and Django saw an invalid token.

**Fix.** Removed the extra `X-CSRFToken` parameter from the refresh and logout views (`accounts/views.py`). Swagger's automatic header is enough, and the frontend sends it from `lib/api.ts`.

**Regression tests.** `test_refresh_after_logout_returns_401` (logout returns 204, then the old refresh token is rejected) and `test_user_post_without_csrf_token_is_rejected` (403 without the header, success with it).

**Side discovery.** A later `GET /me` returned 401 because more than 15 minutes had passed. The access token had expired, which confirmed expiry works. It is now covered by `test_expired_access_token_returns_401`.

## 7. Verification

- `python manage.py check`: no issues
- `python -m pytest -v`: **56 passed** (screenshot in README)
- `npm run lint`: no errors · `npm run build`: compiled successfully, all 8 routes built
- Manual click-through of every page (signup, login, profile, admin login, dashboard, detail) in light and dark mode: everything worked. The member access token expires after 15 minutes and the admin session after 30 minutes of inactivity, which forced a fresh sign-in exactly as designed.
- **EXPLAIN** (README): for `status='active'` (about 89% of rows) Postgres chose a sequential scan, because reading the whole small table is cheaper. For the selective `status='deactivated'` filter it used `profile_status_created_idx`. The index helps selective filters, not the common case.

## 8. What I'd do differently next time

- I wouldn't split the build half-manual, half-AI. I spent 2–3 days writing code step by step with chat guidance and only then moved to Claude Code. Next time I would plan with AI first, then give an agent a strong structured prompt from the start, and spend my own time on reviewing, testing and understanding the code.
- I would write the structured prompt early instead of trying to pass long chat links, which the agent couldn't read.
- I would keep a prompt log and commit after every small working step from the first minute.
