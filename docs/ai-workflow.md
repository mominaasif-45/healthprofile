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
- `python -m pytest -v`: **51 passed** (screenshot in README)
- `npm run lint`: no errors · `npm run build`: compiled successfully, all 8 routes built
- Manual click-through of every page (signup, login, profile, admin login, dashboard, detail) in light and dark mode: everything worked. The member access token expires after 15 minutes and the admin session after 30 minutes of inactivity, which forced a fresh sign-in exactly as designed.
- **EXPLAIN** (README): for `status='active'` (about 89% of rows) Postgres chose a sequential scan, because reading the whole small table is cheaper. For the selective `status='deactivated'` filter it used `profile_status_created_idx`. The index helps selective filters, not the common case.

## 8. What I'd do differently next time

Before asking the AI for anything, I would read the requirements properly first. Each week’s assignment builds on the last, so I would check whether anything in Week 1 needs fixing or changing before I start Week 2.

## Week 2

### W2.1 Tools

- Claude Code did the Week 2 implementation work in the repo, following the rules in `CLAUDE.md`.

### W2.2 Context management

- All of Week 2 ran in one Claude Code session, so the plan, the decisions and the project rules stayed in the same context from start to finish.

### W2.3 Prompt

- I used the master prompt as written, without rewording it between phases.

### W2.4 Blast radius

- Each phase began with a plan, and I approved it with “go” every time before any code was written.
- `CLAUDE.md` limits each phase to its own files, allows new migrations only, and forbids commits and pushes by the agent.

### W2.5 What I checked by hand

- `python -m pytest`: 223 tests passed on both repos.
- After my mentor's Week 1 review: `python -m pytest` 224 passed (one new test for CSRF on member login), and `npm test` (Vitest + Testing Library) 11 passed. The confirm dialog's keyboard behaviour, first checked only by hand, now has automated tests. They also cover the review case: deactivating or reactivating the last profile that matches the filter used to leave keyboard focus on the page body; it now lands on the "Member profiles" heading. The same fix covers deleting an emergency contact (focus lands on the "Emergency contacts" heading) and deleting the whole profile (focus lands on the "Create your wellness profile" heading), and while a confirm dialog is busy, focus stays on the dialog box.
- A clean-clone check, documented in the README under “Verified from a clean clone”.
- I looked at the database directly instead of trusting the model or the code (see W2.6).

### W2.6 Bugs and fixes

- **Shadowed index (`audit/0002`):** `audit/migrations/0002_drop_redundant_fk_indexes.py` removes the redundant automatic index on `AuditEvent.actor`.
- **Primary-contact constraint (`profiles/0006`):** dropping the redundant index on `EmergencyContact.profile_id` in `profiles/0005` also removed the partial unique index `contact_one_primary_per_profile`, because both sit on the same column. The model still declared the constraint, so `makemigrations` saw no difference. `profiles/0006_restore_one_primary_contact_constraint.py` removes and re-adds the constraint so the index is back in the database.

### W2.7 Differently

- Before asking the AI for anything, I would read the requirements properly first. Each week’s assignment builds on the last, so I would check whether anything in Week 1 needs fixing or changing before I start Week 2.

### My reflection

**Hardest part:** When I removed an index, the “only one primary contact” rule disappeared on its own. This was the hardest part for me, because the problem wasn’t visible anywhere. The model still said the rule existed, the code looked correct, and the app looked fine. I only found out when I looked at the database and saw that two contacts were marked as primary at the same time.

**Bug I understood best:** During the fresh setup, the system showed “No migrations to apply”. The .env file was still pointing to the main database instead of the new, fresh one. The main database already had every migration, so there was nothing new to apply, and the setup was not testing a clean database. I fixed this by changing the database name in .env to healthprofile_fresh. After that, every migration showed OK, which confirmed that the setup used the correct database.

**What I’d do before asking AI next time:** Before asking the AI for anything, I would read the requirements properly first. Each week’s assignment builds on the last, so I would check whether anything in Week 1 needs fixing or changing before I start Week 2.

**Part of the code I can explain:** I can tell whether a profile is complete by looking at the completeness percentage on the dashboard, without looking at the code. The number is worked out from four sections, each worth 25%: demographics, at least one emergency contact, wellness preferences, and at least one wellness goal. Each time a section is saved, the app counts how many are filled in and updates the stored percentage.

**Part I don’t fully understand yet:** I don’t fully understand how database constraints prevent incorrect or invalid data from being saved. I know that a constraint is a rule the database enforces, and that the “one primary contact” rule was lost when an index was removed. But I’m not yet clear on how the database decides which rule applies to which table, or what happens when two rules conflict.

## Week 2 review response

My mentor reviewed PR #3 at `9784e4d` with five code points and feedback on the Loom recording. This section records
how the fixes were made on the same branch. The commit-by-commit mapping is in the README ("Review response (PR #3)")
and the real output is in [docs/evidence/week2-review.md](evidence/week2-review.md).

### Who did what

- **The prompts** below were drafted with help from Claude in a separate chat. They are not written by me alone.
- **I made the decisions** in them, chose between the options each plan offered, and approved every plan with "go"
  before any code was written. I decided when each commit was pushed.
- **Claude Code** worked in the repository in one session: it read the code, wrote each plan, wrote the tests first,
  implemented, ran the checks and made one commit per step, following `CLAUDE.md`. It never read `.env`, added no
  dependency, merged nothing and opened no PR.

### Prompt history (as sent in the session)

<details><summary>1. Start: rules and the five phases</summary>

```text
I'm Momina, a full-stack intern. My mentor reviewed my Week 2 PR #3 (branch feature/week2-profiles-audit, commit 9784e4d). I want to fix every code point in his review on this same branch, so PR #3 updates. His full review is at the end of this message.

Rules:
- Work in 5 phases, in this order: (1) audit durability, (2) phone normalisation, (3) permission re-check after the profile lock, (4) primary-contact rule, (5) evidence and handoff.
- Before changing code in each phase, give me a short plain-language plan: what you will change, which files, and why. Wait for my "go". Then implement.
- After each phase: add the tests the mentor asked for, run the relevant tests, and tell me in plain words what changed and what each new test checks. I have to explain it in a video. Make one commit per phase with a clear message, and show the hash. Don't push until I say so.
- Prove each new test: it must fail on the old code and pass on the new code. Show me that.
- Don't weaken or delete existing tests or constraints. Don't touch .env, don't print secrets, don't merge anything, and don't open a new PR.
- Don't expand scope. No new features.

Phase details:
1. Audit durability: the mutation, the completion recalculation and the required audit write must be in one transaction. A required audit failure must roll the whole change back. Wrapping the existing exception-swallowing logger in atomic is not enough. Add failure-injection tests, including profile deletion, that prove complete rollback.
2. Phone numbers: normalise before validation, storage and duplicate checks. Store one canonical form and enforce a deliberate digit-count range. A value like `1------` must be rejected. Tests: punctuation-heavy input, equivalent formats of the same number, duplicate PATCH, and the fourth-contact limit. Check whether existing stored data needs a migration, and tell me before writing one.
3. Permission re-check: after acquiring the profile lock, re-check the active status using fresh state, inside the same transaction. Use one consistent locking policy for the admin deactivate/reactivate path too. Add a PostgreSQL concurrency test that pauses the member request around an admin deactivation and checks the outcome and the audit result. Keep the existing parent lock for the contact limit. Tell me which policy you chose and why.
4. Primary contact: a non-empty contact list must always have a primary. Reject setting is_primary=false on the current primary (with a clear error), unless you can show a safer atomic switch. Tell me both options and your recommendation in the plan, and wait for my choice. Test the invariant, not only the partial unique constraint.
5. Evidence and handoff: show a database catalog check of the primary-contact index and an attempted second primary being rejected. Update the README and docs/ai-workflow.md with the real findings, including the human corrections I made, and state that ORM guards are only application-level append-only protection, so direct database access needs its own restrictions. Check for overlap with Week 1 PR #2 (don't merge it). Run the final migrations, backend tests, frontend tests and build on the resulting branch, and tell me the exact commit that was tested.

Start with Phase 1: read audit/services.py, the member views and the services, then give me your plan. Don't write code until I say go.

my mentors review
[the mentor's full review was pasted here]
```
</details>

<details><summary>2. Phase 1 decision</summary>

```text
go. Yes to both: include admin deactivate/reactivate, and use 503 audit_unavailable. Two additions: (1) in the README, document which audit events are required (fail closed) and which are best-effort, and why. (2) Show me the failing-then-passing proof output when you’re done. Don’t push yet.
```
</details>

<details><summary>3. Phase 2 plan request</summary>

```text
Good. Push 6a5633f to feature/week2-profiles-audit, then start Phase 2 (phone normalisation). Check the serializer, the model and the phone values already stored, then bring me the plan before writing code. Please also tell me if the new canonical format would change any existing stored numbers.
```
</details>

<details><summary>4. Phase 2 decision</summary>

```text
go A. Two additions: (1) after the migrations, query the PostgreSQL catalog to show that contact_phone_is_canonical and the unique constraint for (profile, phone) both exist, and show an attempted non-canonical insert being rejected. Keep that output for Phase 5. (2) Run makemigrations --check and confirm that 0007 and 0008 don’t remove or change any existing constraint by accident. Show me the fail-then-pass proof as before. Commit as Phase 2 and don’t push until I say so.
```
</details>

<details><summary>5. Phase 3 plan request</summary>

```text
push 15f7b1b
```

```text
Push 15f7b1b to feature/week2-profiles-audit. Then start Phase 3 (permission re-check after the profile lock). Read the member views, get_profile, services._lock and the admin deactivate/reactivate path, then bring me the plan before writing code. In the plan, please explain: (1) which locking policy you recommend for admin transitions and member writes, and why; (2) what the member gets when the profile was deactivated while the request waited (status code and message); (3) what the audit outcome should be in that case, remembering the denied-write audit must not be undone by the rollback; (4) how you’ll write the PostgreSQL concurrency test in a reliable way, without flaky timing. Explain it in plain words.
```
</details>

<details><summary>6. Phase 3 decision</summary>

```text
go. Two additions: (1) after the tests pass, run tests/test_concurrency.py 20 times in a row and show me that every run passes (to prove they’re not flaky); (2) check that leftover thread connections can’t leave locks or open connections behind, even when a test fails or times out. Give me the fail-then-pass proof as before, and explain each scenario in plain words. Commit as Phase 3 and don’t push until I say so.
```
</details>

<details><summary>7. Phase 4 plan request</summary>

```text
Push b8dd91a to feature/week2-profiles-audit. Then start Phase 4 (the primary-contact rule). Read update_contact, create_contact and delete_contact, then bring me the plan before writing code. Please explain both options in plain words: (a) reject setting is_primary=false on the current primary, and (b) switch primary atomically in one step. Tell me which you recommend and why, what the member sees in each case, and how it affects the frontend’s edit contact form. I will choose.
```
</details>

<details><summary>8. Phase 4 decision</summary>

```text
Go with option (a), and the ContactsCard.tsx change is approved (disable the checkbox when editing the current primary, show the hint, and show an is_primary error under it). Write the tests first, including the invariant test that checks after every step that a profile with contacts has exactly one primary. Give me the fail-then-pass proof. Run the backend tests, npm test, lint, type-check and npm run build. Say plainly in the README that ‘at least one’ is enforced in the service and ‘at most one’ by the database. Commit as Phase 4 and don’t push until I say so.
```
</details>

<details><summary>9. Phase 5 plan request</summary>

```text
Push 3c58e99 to feature/week2-profiles-audit. Then do Phase 5 (evidence and handoff), and also add the frontend phone check to this phase: update frontend/lib/validation.ts to use the same rule as the server (optional leading +, digits, spaces, brackets and dashes, 7 to 15 digits) with a small test. Then give me a plan before changing anything. The plan should cover: (1) the database evidence: the catalog check for the primary-contact index and the phone constraint, plus an attempted second primary through raw SQL being rejected after the migrations; (2) checking overlap with Week 1 PR #2 without merging it, using a throwaway test merge (for example on a temporary local branch) and telling me exactly which files conflict and how you’d resolve them; (3) a README and docs/ai-workflow.md update with the real prompt history, the human corrections I made (for example my decisions in Phases 1, 3 and 4) and honest statements of the limits, including that the ORM guards are only application-level append-only protection and that direct database access needs its own restrictions; (4) a short ‘Review response’ section mapping each of my mentor’s five code points and Loom points to the commit that addresses it; (5) running the final migrations, backend tests, frontend tests and build on the resulting branch and naming the exact tested commit. Don’t merge anything and don’t change code until I say go.
```
</details>

<details><summary>10. Phase 5 decision</summary>

```text
go. Answers: 1 yes, 2 yes, 3 yes, 4 two commits (first the frontend phone check, then docs and evidence). One correction for docs/ai-workflow.md: the prompts I sent you were drafted with help from Claude in a separate chat. I made the decisions and approved each plan. Write that plainly, and don’t describe the prompts as written by me alone. Keep everything else factual, and quote only what really happened in this session. Don’t push until I say so, and give me the exact tested commit at the end.
```
</details>

### My decisions and corrections

| Phase | Options I was given | What I decided or added |
|---|---|---|
| 1 Audit durability | Include admin deactivate / reactivate or not (it went beyond review point 1); the response for a failed audit | Included the admin path; 503 `audit_unavailable`; added: document required vs best-effort audit events in the README, and show the fail-then-pass output |
| 2 Phone normalisation | A: normalise + data migration + database CHECK (needs phone literals in existing test setup updated to the canonical form) · B: no database constraint | Chose **A**; added: a catalog check and a rejected raw insert, kept for Phase 5, and `makemigrations --check` plus confirmation that `0007` / `0008` change no existing constraint |
| 3 Lock and re-check | Locking policy, response, audit outcome and test approach as proposed | Approved; added: 20 consecutive runs of the concurrency tests, and a check that leftover thread connections cannot leave locks or connections behind, even when a test fails or times out |
| 4 Primary contact | (a) reject unsetting the current primary · (b) hand the primary to the oldest other contact automatically | Chose **(a)**; approved the `ContactsCard.tsx` change (outside the earlier backend scope); asked for the README to say plainly that "at least one" is in the service and "at most one" in the database |
| 5 Evidence and handoff | One or two commits; a throwaway database; a temporary merge branch; an evidence file | Added the frontend phone check to this phase; chose two commits; approved the throwaway database, temporary branch and evidence file; corrected this document so the prompts are not described as written by me alone |

### What the checks caught

My rule that every new test must fail on the old code and pass on the new code, and the extra checks I asked for,
surfaced these during the session:

- **Phase 3, plan corrected by the old-code run.** The plan predicted that scenario C (admin waits for the member's lock)
  would fail on the old code. It passed: the old admin `UPDATE` also waited for the member's row lock. Claude Code
  reported this; scenario D (two admins at once), added while writing the tests, is the one that fails on the old
  admin path. C stays as a regression guard.
- **Phase 3, the 20-run check.** The first batch of 20 runs had 1 error and a second batch had 2. They came from the
  test's own leftover-lock check: a diagnostic showed autovacuum locking the system table `pg_trigger` on the freshly
  created test database. The check was narrowed to client connections, then 20 / 20 runs passed. A deliberate-failure
  demo (a failing test holding a lock, and a thread stuck past its join timeout) left 0 sessions and 0 locks behind.
- **Tests that pass on the old code are labelled, not hidden.** 9 of 25 phone tests and 3 of 7 primary-contact tests
  passed on the old code because that behaviour was already correct; in the frontend phone test, 4 of the 6 old-code
  failures were only the changed message.
- **Smaller mistakes fixed before commit.** A garbled assertion and a colliding test contact in the Phase 2 migration
  test (fixed before the first run); stray backslashes in a README quote (Phase 4); in Phase 5 an evidence-script
  edit failed and the unedited script hit a wrongly guessed column. It ran inside a transaction, so it was rolled back
  and nothing was written; the script was rewritten.
- **A gap flagged for me to decide.** After Phase 4, Claude Code pointed out that the frontend phone check still used the
  old pattern (out of scope at the time). I added it to Phase 5.

### Limits (stated honestly)

- **Audit append-only is application-level only.** The ORM guards and the lack of an API route stop the application's
  own code. Raw SQL can still update or delete audit rows (shown in the evidence file), so direct database access needs
  its own restrictions, such as a database role without `UPDATE` / `DELETE` on the audit table, or triggers.
- **"At least one primary contact" is enforced only in the service**; the database enforces "at most one". Raw SQL can
  leave a profile without a primary (shown in the evidence file).
- **Phone numbers have no country rules**: `0300 1234567` and `+92 300 1234567` are different numbers here.
- **Required audit events fail closed**: if the audit table cannot be written, edits are refused with 503.
- **Week 1 PR #2 is not merged.** A throwaway merge showed every conflict resolves to this branch's file; merging is left
  to my mentor.
