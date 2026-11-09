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
- **Claude Code** worked in the repository in one session (plus a follow-up session for prompts 11 to 13): it read the code, wrote each plan, wrote the tests first,
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

**Follow-up session (2026-11-04): contact deletion race.** My mentor's review of the Week 3 PR asked for this inherited
Week 2 race to be fixed before the stack is merged. Prompts 11 to 13 were sent in a new Claude Code session on this branch.

<details><summary>11. Follow-up plan request (drafted with help from Claude in a separate chat)</summary>

```text
New task on the Week 2 branch (PR #3). My mentor’s review on the Week 3 PR says: ‘Before merging the stack, fix the inherited contact deletion race: a contact can become primary after the view reads it but before the delete acquires the profile lock. Re-read the owned contact under the lock, handle concurrent removal as 404, and add a deterministic PostgreSQL test that checks primary promotion, completion and audit events.’

Plan only. Do not change anything yet. Please:

Find the delete-contact code (view and service) and explain the race in plain words, pointing at the exact lines.
Propose the fix: re-read the contact by id and owner after taking the profile lock, and return 404 if it is gone.
Propose the deterministic test, using threading events like our existing concurrency tests: how it forces the exact order (pause the delete after the view’s read and before the lock, make the contact primary in another thread, then release), and what it asserts after the race (exactly one primary, completion state, audit events with field names only).
Say how we will show the new test failing first against the current code, then passing.
List which files change, the blast radius, and whether Week 1 or Week 3 code is touched.
This message was drafted with help from Claude in a separate chat; please log it.

Don’t commit and don’t push.
```
</details>

<details><summary>12. Follow-up decision (drafted with help from Claude in a separate chat)</summary>

```text
Go. Answers: include the update_contact fix with its own test. Tests first: show me E and F failing on the current code with the -rs output, then make the fix and show them passing. Then run the full backend suite, tests/test_concurrency.py 20 times in a row, and makemigrations --check, and show me the real outputs. Add the evidence to docs/evidence/week2-review.md and the README review-response table, and update the test docstring. Log this message as prompt 12 and your plan request as prompt 11, both marked ‘drafted with help from Claude in a separate chat’. For Week 3 we will merge (not rebase) later; do not touch the Week 3 branch. Commit only after I approve your report. Do not push.
```
</details>

<details><summary>13. Follow-up approval (drafted with help from Claude in a separate chat)</summary>

```text
Approved. Log this message as prompt 13 in the same commit, marked ‘drafted with help from Claude in a separate chat’, then commit with fix(contacts): re-read the contact under the profile lock; concurrent removal is 404. Then push feature/week2-profiles-audit (no force) so PR #3 updates, and show me git status and the full commit hash. Also draft a short comment for me to post on PR #3 that names the commit hash, says what the race was in two sentences, says I also fixed the same race in update_contact (it returned a 500), and gives the test counts (278) and the 20-of-20 result. Do not touch the Week 3 branch.
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
| Follow-up: contact deletion race | Also fix the same gap in `update_contact` (a PATCH losing to a delete gave 500), which the mentor had not asked for, or leave it | Included it with its own test (G); asked for E and F to be shown failing first with `-rs`, the full suite, 20 consecutive concurrency runs and `makemigrations --check`; Week 3 will take the fix by a merge (not a rebase) later, and its branch is not touched |

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
- **Follow-up, a second gap found while planning.** Reading `update_contact` for the deletion-race plan showed that a
  PATCH losing the race to a delete crashed with a 500. Claude Code flagged it as outside the mentor's request; I chose
  to include it. Test G proved the 500 on the old code before the fix.

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

## Week 3: Machine Learning Pipeline and Prediction API

Week 3 adds an educational ML prototype: a seeded synthetic appointment dataset, a leakage-safe training pipeline, a
versioned prediction endpoint and a clearly labelled dashboard card. It was built in a separate git worktree on
`feature/week3-ml-pipeline`, started from `feature/week2-profiles-audit` at `96e29a2` (PR #3 still under review), with
its own database `healthprofile_week3`.

### Who did what

- **The master prompt, the Phase 0 prompt, my answers to the Phase 0 questions and my phase decisions** (each marked
  below) were drafted with help from Claude in a separate chat. They are not written by me alone. I made the decisions in them and approve every phase with "go".
- **Claude Code** works in the repository in one session: it reads the code, writes each plan, writes the tests first,
  implements, runs the checks and commits each phase only after I approve it. It does not read `.env`, merge or push.

### Prompt history (as sent in the session)

<details><summary>1. Master prompt and Phase 0 request (drafted with help from Claude in a separate chat)</summary>

```text
I'm Momina, a full-stack AI/ML intern. Project: HealthProfile (Django REST + PostgreSQL backend, Next.js frontend). This folder is a git worktree on branch feature/week3-ml-pipeline, started from feature/week2-profiles-audit at 96e29a2 (Week 2 PR #3 is under review and not merged). It has its own database, healthprofile_week3. Week 3 assignment: "Machine Learning Pipeline and Prediction API", an educational prototype using synthetic, non-sensitive data.

Requirements:
- Synthetic data only. Document provenance (generated by a seeded script), license (none needed, generated), schema and limitations. State honestly that synthetic data follows rules we wrote, so metrics show the method working and say nothing about real clinics.
- Exploratory analysis, missing-value handling, train/validation/test split, and no data leakage (split first, fit preprocessing only on training data, no features derived from the outcome).
- Task: non-diagnostic synthetic appointment no-show likelihood. Features come from fictional appointment data, never from my real profile data.
- A baseline model and at least one improved scikit-learn model. Compare with appropriate metrics (including for class imbalance) and do error analysis.
- Save preprocessing and model together as one reproducible scikit-learn Pipeline artifact.
- A training script that reproduces the artifact (fixed random seeds, pinned dependencies in requirements.txt). The venv uses Python 3.13.
- A versioned inference endpoint that validates the input schema, rejects malformed and out-of-range inputs, and returns the prediction, a probability and the model version. Follow the existing API conventions, auth and error format.
- Show the model output in the existing dashboard (Next.js), clearly labelled as an educational demo, never as medical advice or diagnosis.
- Keep all Week 1 and Week 2 features working. Add tests. Document trade-offs.
- README: feature checklist, architecture decisions, run/test commands, metrics, dataset limitations and bias, sample request and response, limitations.

How we work:
- Stay on this branch. Don't merge anything, don't touch the other folders, don't touch .env or print secrets. No new features beyond the brief.
- Work in phases and stop after each one: (1) synthetic data generator and data documentation, (2) analysis, missing values and split, (3) baseline and improved models, metrics and error analysis, (4) pipeline artifact and reproducible training script, (5) inference endpoint with validation and tests, (6) dashboard card, (7) README, evidence and final validation.
- Before each phase, give me a short plain-language plan and wait for my "go". After each phase, explain in plain words what changed and why. I must explain it in a video.
- Add tests first where possible, and show me that new tests fail on the old code and pass on the new.
- One commit per phase with a clear message. Don't push until I say so.
- Keep a running log of my prompts and decisions in docs/ai-workflow.md. Be honest about which prompts were drafted with help from Claude in a separate chat.

Start with Phase 0: read the repo structure, the existing API conventions and the dashboard, then give me an overall plan and the questions you need me to answer. Don't write code yet.
```
</details>

<details><summary>2. Answers to the Phase 0 questions and Phase 1 plan request (drafted with help from Claude in a separate chat)</summary>

```text
Answers: 1 yes, add scikit-learn, numpy, pandas and joblib with exact pins, no matplotlib or Jupyter. 2 signed-in members only, throttled, as you recommend. 3 yes, one commit per phase after I approve it, never push. 4 approved. 5 yes, commit the dataset and model file, but the code must verify the SHA-256 checksum before loading the joblib file (it is a pickle), and the README must explain why. 6 on the /profile dashboard below the wellness card. 7 The master prompt, the Phase 0 prompt and these answers were drafted with help from Claude in a separate chat; I made the decisions and approve each step. Your defaults are fine (predictions not audited or stored, about 6,000 rows with about 20% no-shows, version noshow-1.0.0).

Two additions to the plan: (a) in Phase 1, include an adjustable noise level in the generator, and in the data card say honestly that synthetic data follows rules we wrote, so scores will look better than real life; if the models score suspiciously near-perfect, tell me and we'll add noise. (b) In Phases 3 and 7, report metrics by group (age band, booking channel, distance band) and document any dataset bias and class imbalance, as the brief requires.

Go. Give me the Phase 1 plan first and wait for my 'go' before writing code.
```
</details>

<details><summary>3. Phase 1 decision (drafted with help from Claude in a separate chat)</summary>

```text
go. One addition: in the data card, state clearly that the age-band, channel and other differences in the generating rule are arbitrary choices to give the bias checks something to find, and are not claims about real people or populations. Also explain the 'best possible score' in plain words in your report. Don't commit until I approve.
```
</details>

<details><summary>4. Phase 1 approval and Phase 2 plan request (drafted with help from Claude in a separate chat)</summary>

```text
Good report. Keep noise at 1.0. Yes, my Phase 1 'go' message was also drafted with help from Claude in a separate chat; please mark it that way in the log. Commit Phase 1 with your proposed message, don't push, and show me the commit hash. Then bring me the Phase 2 plan (analysis, missing values and split) and wait for my 'go'.
```
</details>

<details><summary>5. Phase 2 decision (drafted with help from Claude in a separate chat)</summary>

```text
go. Yes, my last message (the Phase 1 approval and Phase 2 plan request) was also drafted with help from Claude in a separate chat; please mark it that way in the log. Write the tests first, show them failing, then passing. Run the full suite, show git diff --stat and a plain-language report, and don't commit until I approve.
```
</details>

<details><summary>6. Phase 2 approval and Phase 3 plan request (drafted with help from Claude in a separate chat)</summary>

```text
Good report. Commit Phase 2 with your proposed message, don't push, and show me the commit hash. Then bring me the Phase 3 plan (baseline and improved models, metrics, error analysis). In the plan, explain in plain words: how you will choose the decision threshold on the validation pile; how the 'best possible score' of 0.657 will be used as a leakage alarm; how you'll report the by-group results honestly given the small groups; and what you'll say if the complex model isn't clearly better than logistic regression. Wait for my 'go'.
```
</details>

<details><summary>7. Phase 3 decision (drafted with help from Claude in a separate chat)</summary>

```text
Good plan. Answers: 1 best F1 on validation. 2 no, skip the age_band experiment; put it in the README as possible future work. 3 yes, the Phase 2 approval and Phase 3 plan request were drafted with help from Claude in a separate chat; please log it. One change: the leakage alarm should allow for sampling luck, because the ceiling is calculated on the same finite pile and an honest model can slightly exceed it by chance. Alarm if a model exceeds that pile's ceiling by a margin of 0.03, or if any ROC-AUC is above 0.90. Explain the margin in the report. Also keep the experiment fast, and if the retraining test makes the suite much slower, mark it so it can be skipped with a flag but still runs by default in CI-style runs. Go. Tests first, show them failing then passing, explain with the real numbers in plain words, and don't commit until I approve.
```
</details>

<details><summary>8. Phase 3 approval, log correction and Phase 4 plan request (drafted with help from Claude in a separate chat)</summary>

```text
Commit Phase 3 with your proposed message, don't push, and show me the commit hash. Log correction: yes, my Phase 3 'go' message was drafted with help from Claude in a separate chat, and the 0.03 leakage-margin idea was suggested by Claude in that chat; I reviewed and approved it. Please log it that way and not as my own decision. Then bring me the Phase 4 plan (pipeline artifact and reproducible training script), and wait for my 'go'. In the plan, explain: what exactly goes into the artifact file and its metadata; how the SHA-256 check works before loading; what 'reproduces' means (same predictions? same file bytes?) and how we test it; and the security note about joblib files being pickles.
```
</details>

<details><summary>9. Phase 4 decision (drafted with help from Claude in a separate chat)</summary>

```text
Answers: 1 yes, add .gitattributes with *.joblib binary. 2 ship the model fitted on the training rows only; note in the README that a production system would refit on all the data and re-derive the threshold. 3 yes, my last message (the Phase 3 commit, the log correction and the Phase 4 plan request) was drafted with help from Claude in a separate chat; please log it. Go. Tests first, shown failing then passing. Show the byte-identity result, run the full suite, explain in plain words, and don't commit until I approve.
```
</details>

<details><summary>10. Phase 4 approval and Phase 5 plan request (drafted with help from Claude in a separate chat)</summary>

```text
Good. Yes, my Phase 4 'go' message was drafted with help from Claude in a separate chat; please log it. I checked the EXPECTED_SHA256 line myself against Get-FileHash and it matches. Commit Phase 4 with your proposed message, don't push, and show me the commit hash. Then bring me the Phase 5 plan (the versioned inference endpoint with validation and tests) and wait for my 'go'. In the plan, explain: the URL, request and response shapes; how validation reads the schema in the metadata; what happens with malformed, out-of-range and extra fields; how the model is loaded once (and what happens if loading fails); auth, CSRF and the throttle; what is not logged; and the Swagger documentation.
```
</details>

<details><summary>11. Phase 5 decision (drafted with help from Claude in a separate chat)</summary>

```text
Answers: 1 yes, members without a profile or with a deactivated profile may use the demo. 2 yes, 30 per minute per member. 3 yes, my last message (the Phase 4 commit and the Phase 5 plan request) was drafted with help from Claude in a separate chat; please log it. Go. Tests first, shown failing (404) then passing. Run the full suite, show git diff --stat, explain in plain words with one real example request and response, and don't commit until I approve.
```
</details>

<details><summary>12. Phase 5 approval, push and Phase 6 plan request (drafted with help from Claude in a separate chat)</summary>

```text
Good. Yes, my Phase 5 'go' message was drafted with help from Claude in a separate chat; please log it. Commit Phase 5 with your proposed message and show me the hash. Then push the branch feature/week3-ml-pipeline to origin as a backup (it's a new branch; don't open a PR, don't touch feature/week2-profiles-audit, and don't force anything). Then bring me the Phase 6 plan (the dashboard card). In the plan, explain: where the card goes on /profile; the form fields, their prefilled fictional values and how blanks are handled; how the card calls the API with the existing api() helper, including CSRF and the 401, 403, 429 and 503 states; the disclaimer and wording (no medical claims); accessibility and keyboard behaviour; and the Vitest tests. Wait for my 'go'.
```
</details>

<details><summary>13. Phase 6 decision (drafted with help from Claude in a separate chat)</summary>

```text
Answers: 1 yes, hide the card when there is no profile, and note it in the README as a design choice. 2 yes, add the side-menu link. 3 yes, my last message (the Phase 5 commit, the push and the Phase 6 plan request) was drafted with help from Claude in a separate chat; please log it. Go. Tests first, shown failing then passing. Run npm test, lint, build and the backend suite. Then give me exact manual steps to try the card in the browser myself with both servers running: the normal case, a 400 case, the keyboard-only path, light and dark theme, and how to see the 429 and 503 messages if that's practical. Don't commit until I approve.
```
</details>

<details><summary>14. Phase 6 log mark and manual test (drafted with help from Claude in a separate chat)</summary>

```text
Yes, my Phase 6 'go' message was also drafted with help from Claude in a separate chat. Please mark it in the log. I'm trying the card by hand now. Don't commit until I say so.
```
</details>

<details><summary>15. Phase 6 approval after the manual test (drafted with help from Claude in a separate chat)</summary>

```text
I tried the card by hand: normal case, 91 check, keyboard only, light and dark. All fine. Please commit Phase 6, then show me the commit hash and git status
```
</details>

<details><summary>16. Phase 7 plan request (drafted with help from Claude in a separate chat)</summary>

```text
Phase 7 plan, please. Do not write or change anything yet. The Week 3 brief needs a README with: a feature checklist, architecture decisions, run and test commands, the metrics, dataset limits and bias, a sample request and response, and limitations. Please propose: (1) the README Week 3 section outline, in plain words, including the design choices we made (the card is hidden without a profile, logistic regression chosen over the fancier model, the pickle hash check, the threshold chosen on validation only, the test set used once, and the age_band idea left as future work); (2) which screenshots to take and who takes them, using the two card screenshots we already have; (3) the final validation list (migrations check, backend tests, frontend tests, lint, build) and how we name the tested commit; (4) what goes into docs/ai-workflow.md; (5) whether you recommend opening a Week 3 pull request, and what its base branch should be, since the Week 2 branch is not merged. Also tell me which of my messages need the 'drafted with help from Claude in a separate chat' mark. Don't commit anything.
```
</details>

<details><summary>17. Phase 7 decision (drafted with help from Claude in a separate chat)</summary>

```text
Go for Phase 7. The outline you proposed is approved as written.

Answers to your questions:

Messages 14, 15, 16 and 17 were all drafted with help from Claude in a separate chat. Please log and mark them.
PR #3's base is main. I checked it on GitHub.
A Week 3 pull request on top of the Week 2 branch is approved, but do not open it yet. First, show me the final validation results.
I have added card-result.png, swagger-week3-request.png and swagger-week3-responses.png to docs/screenshots/week3/ next to the two existing ones (card-light.png and card-dark.png). Please use all five in the README screenshots table with a plain-words caption each. Please check with dir that all five files exist before you use them, and tell me if any is missing.
Leave the 'My reflection' heading in docs/ai-workflow.md empty. I will write it myself in my own words. Leave a clearly marked placeholder for my Week 3 Loom link in the README.
Please push feature/week3-ml-pipeline now as a backup (no force push, no pull request yet).

How to work:

Write the README section and the evidence file first, then show me the outline of the README section in your report.
Run the whole validation list on the final commit with a clean working tree, without ML_SKIP_SLOW, and show me the real outputs.
Tell me the tested commit hash only after the validation has passed on that exact commit.
Commit with the message you proposed only after I approve your report. Do not push anything else and do not open the PR.

Please report in plain words.
```
</details>

<details><summary>18. Correction to the screenshot names (drafted with help from Claude in a separate chat)</summary>

```text
Correction to point 4 of my last message: the two Swagger screenshots are actually named swagger-request.png and swagger-responses.png (not swagger-week3-request.png and swagger-week3-responses.png). Please run dir docs\screenshots\week3 to confirm the exact names and extensions, and use the real names in the README table. All five files exist: card-light, card-dark, card-result, swagger-request, swagger-responses.
```
</details>

<details><summary>19. Phase 7 approval (drafted with help from Claude in a separate chat)</summary>

```text
Approved. Message 18 was drafted with help from Claude in a separate chat; please mark it, and log this approval message (19) with the same mark. Commit Phase 7 with the message you proposed, then re-run all ten checks on that exact commit with a clean working tree. Show me the real outputs and give me the tested commit hash only if everything passes. Do not push anything and do not open the PR yet.
```
</details>

<details><summary>20. Push and PR draft (drafted with help from Claude in a separate chat)</summary>

```text
Push feature/week3-ml-pipeline to GitHub now (no force push). Then show me git status and git log --oneline -3. Do not open a PR. Please also draft the PR title and description for me to paste on GitHub later: base feature/week2-profiles-audit, stacked on #3 (please merge #3 first), the tested commit, the validation summary in a short table, and links to the README section and docs/evidence/week3.md. Leave a placeholder for my Loom link.
```
</details>

<details><summary>21. Loom link and reflection (drafted with help from Claude in a separate chat)</summary>

```text
Here is my Week 3 Loom link: https://www.loom.com/share/9d6433ae55664ab89026f9e7df4299b4

Please:

Replace the Week 3 Loom placeholder in the README with this link.
I have written my reflection myself under 'My reflection' in docs/ai-workflow.md and saved it. Do not edit, rewrite or improve it; only commit it as it is.
Log this message in docs/ai-workflow.md as the next prompt, marked 'drafted with help from Claude in a separate chat'.
Before committing, show me git diff --stat and confirm that only documentation files changed, with no code.
After I approve, commit with the message docs: add Week 3 Loom link and reflection.
Re-run python manage.py makemigrations --check --dry-run, python -m pytest, npm test, npm run lint and npm run build on that exact commit with a clean tree, and show me the real outputs. Then give me the final tested commit hash.
Rewrite the PR description with the final hash and the Loom link in both places, and update the links to point to the final hash.
Do not push and do not open the PR until I approve.
```
</details>

**Follow-up session (2026-11-04): merging the Week 2 race fix.** My mentor's review of PR #4 asked for the inherited
Week 2 contact deletion race to be fixed before the stack is merged. After the fix was pushed on the Week 2 branch,
prompts 22 to 24 were sent in a new Claude Code session on this branch. At my request, Claude Code made the merge (not a
rebase) and pushed this branch as a backup.

<details><summary>22. Merge the Week 2 race fix (drafted with help from Claude in a separate chat)</summary>

```text
New task on the Week 3 branch (PR #4). My mentor’s review on PR #4 said to fix the contact deletion race on the Week 2 branch before merging the stack. That fix is now pushed as dbe41db58f88afa52f6faad648d14099dbab1aa6 on origin/feature/week2-profiles-audit. Please bring it into feature/week3-ml-pipeline with a MERGE, not a rebase.

Steps:

Run git fetch, then show me what the merge will bring in before you merge.
Do the merge. I expect conflicts in README.md and docs/ai-workflow.md. If there are conflicts, stop and show me each one and your proposed resolution before you finish the merge. Never drop either side: keep the Week 2 follow-up text and my Week 3 text. Update the test counts correctly (Week 2 is now 278, and Week 3 should become 427 backend, 47 frontend).
After the merge, run all of these on that exact commit with a clean tree, and show me the real outputs: makemigrations --check --dry-run, manage.py check, spectacular --validate, python -m pytest (full, without ML_SKIP_SLOW), python -m ml.train --check, the rebuild of the data, analysis and reports followed by git diff --exit-code, npm test, npm run lint and npm run build.
Add the results to docs/evidence/week3.md as a short ‘After the Week 2 race fix’ section, with the final commit hash described as ‘the merge commit’, and log this message as the next prompt, marked ‘drafted with help from Claude in a separate chat’.
Draft the updated PR #4 description with the new final hash.
Do not push until I approve.
```
</details>

<details><summary>23. Merge resolutions approved (drafted with help from Claude in a separate chat)</summary>

```text
Go with all of your proposed resolutions. Before you commit the merge, run a search for leftover conflict markers (<<<<<<<, =======, >>>>>>>) in the whole repo and show me that it finds none. Show me the git diff of README.md. Commit the merge with the message you proposed. Then run the full list on that exact merge commit with a clean tree and show me the real outputs. Then, after my approval, add the evidence section and log this message as prompt 22 (marked ‘drafted with help from Claude in a separate chat’) in a second docs-only commit. Draft the updated PR #4 description. Do not push.
```
</details>

<details><summary>24. Evidence approved, commit and backup push (drafted with help from Claude in a separate chat)</summary>

```text
Approved: use the evidence section as drafted, and also update the ‘Which commit was tested’ note at the top of docs/evidence/week3.md to point to it. Log the merge request as prompt 22 and this message as prompt 23, both marked ‘drafted with help from Claude in a separate chat’. Make the docs-only commit, show me git diff --stat and confirm only documentation changed. Then push feature/week3-ml-pipeline (no force) as a backup and show me git status and the full hash. Do not fill in the PR description yet: more evidence is coming, so I will ask you for the PR description once at the end. Also tell me whether the description of PR #3 on GitHub is likely to mention ‘275’ tests anywhere that I should update (check the README review-response table and any text you wrote for it).
```
</details>

When the numbering in prompts 23 and 24 overlapped, Claude Code asked how to log them, and I chose to log all three
messages as 22 to 24.

<details><summary>25. Stage 3 plan request: mentor's PR #4 evidence points (drafted with help from Claude in a separate chat)</summary>

```text
Stage 3 plan, please. Do not change anything yet. My mentor’s review of PR #4 asks for: (a) a direct API 400 and a wrong-role or CSRF denial added to the demo evidence, because client range validation alone cannot prove server enforcement; (b) a link to the exact AI prompt refinement and the test that failed before the fix; (c) an explanation of the false-reminder / missed-reminder trade-off at the selected 0.22 cutoff, and that the 22% is a decision threshold chosen on validation where an estimate above it suggests an extra reminder, not a certain no-show; (d) a short timestamped clip showing both a successful request and a rejected request.

Please propose:

For (a): which existing tests in tests/test_ml_api.py already prove the 400, the CSRF denial and the wrong-role or unauthenticated denial (names and what they assert), and the exact steps for me to capture REAL responses myself in the browser console with both servers running (success 200, a malformed 400, a request without the CSRF header, and a request from an admin or signed-out session). I need the exact text to paste and the exact status codes we expect.
For (b): which prompt refinement in docs/ai-workflow.md is the best example (with its prompt number and commit), and which test failed before the fix, with its real failing output saved in the evidence file. Link both to the tested commit.
For (c): a short README and model-report paragraph in plain words with our real numbers (precision 29.5%, recall 50.8%, threshold 0.22), and whether we should also change the card’s wording to ‘suggests an extra reminder, not a certain no-show’. If so, list the files and tests that would change. Do not do it yet.
For (d): a step-by-step shot list for a 1 to 2 minute clip with the timestamps I should note, and where to put the link and timestamps in the PR.
Which commits this will add, and how we name the final tested commit.

Also log this message as prompt 25, marked ‘drafted with help from Claude in a separate chat’. Don’t commit and don’t push.
```
</details>

<details><summary>26. Stage 3 decision and C1 (drafted with help from Claude in a separate chat)</summary>

```text
Go for Stage 3. Answers: (1) yes, change the card wording, and I will retake card-result.png myself; (2) Week 2 prompt 12 only; (3) both the admin private window and the signed-out case.

Corrections: (i) do not use the word ‘patient’ anywhere, in the README, the report paragraph or the card. Say ‘the person’ or ‘this fictional appointment’. (ii) In the console snippet, rename URL to ENDPOINT so it can’t clash with the browser’s built-in, and tell me to paste the block only once per page load.

Do C1 first: update the tests first, show them failing, then make the card wording change and the report-paragraph change in experiment.py (numbers computed from the results, not typed in), show them passing, regenerate the report, and run npm test, lint, build and the full backend suite. Show me the real outputs and git diff --stat. Don’t commit until I approve. Then give me the final exact steps for the six console captures, the screenshot retake and the clip. Log this message as prompt 26, marked ‘drafted with help from Claude in a separate chat’. Don’t push.
```
</details>

<details><summary>27. C1 approval (drafted with help from Claude in a separate chat)</summary>

```text
Approved. Commit C1 as proposed (the five code and report files only) with the message feat(ml,frontend): explain the 0.22 cutoff as a reminder threshold, not a certain no-show. Leave the prompt log uncommitted for C2, and log this message as prompt 27, marked ‘drafted with help from Claude in a separate chat’. Leave the older ‘No real patient data’ disclaimers as they are. Show me git status and the full hash. Don’t push.
```
</details>

<details><summary>28. Plan request: PostgreSQL race tests in CI, mentor's PR #3 review (drafted with help from Claude in a separate chat)</summary>

```text
Plan only, change nothing. My mentor’s review of PR #3 asks: ‘Keep these PostgreSQL tests active in a reproducible check/CI job. test_concurrency.py intentionally skips on non-PostgreSQL databases, so a green SQLite run cannot validate this fix. Show the database backend and skip summary in review evidence and fail the dedicated job if the intended race cases do not execute.’ He also asks for the race tests to be run on the Week 3 head, with the tested commit identified. He has said I do not need to record any follow-up clips.

Please propose:

Whether a .github/workflows/ folder already exists, and what we have today.
A GitHub Actions workflow with a PostgreSQL service for tests/test_concurrency.py: which Python and PostgreSQL versions, how the database settings reach Django WITHOUT my .env (throwaway CI-only values written in the workflow, never a real password), how it prints the database backend and server version, and how it FAILS if any race test is skipped or if fewer than the expected number of tests run.
How we prove locally that the guard really fails, for example by running the tests against SQLite and showing the guard logic fails.
A second job for the full backend suite and the frontend tests, if that is cheap, or a reason to leave it out.
The command and real output I should record in the evidence on the final Week 3 head: python -m pytest tests/test_concurrency.py -rs -v, with the database vendor printed.
Which files change, the blast radius (config only, no application code), and the order of commits together with the pending evidence commit (C2: the README paragraph, the six console captures, the new card-result.png caption, and the prompt log).
What I should expect to see on GitHub’s Actions tab after a push, and what could go wrong.

Log this message as prompt 28, marked ‘drafted with help from Claude in a separate chat’. Don’t commit and don’t push.
```
</details>

<details><summary>29. CI decision: race-test job and guard only (drafted with help from Claude in a separate chat)</summary>

```text
Go for the CI work. Answers: (1) yes, add .github/ with the official actions and the postgres:17 image; (2) no extra jobs for now, only the race-test job and its guard, because the mentor asked only for that and the ML tests may differ across operating systems; (3) use -vv; (4) the C2, C3, C4 order is fine.

Please: write the workflow and the guard script as planned, show me the two files, then run section 3 locally (SQLite must make the guard FAIL, the 8-test run must FAIL, the full PostgreSQL run must PASS) and show me the real outputs including the exit codes. Do not commit anything until I approve your report. Log this message as the next prompt, marked ‘drafted with help from Claude in a separate chat’. Don’t push.
```
</details>

<details><summary>30. CI files approved; server-enforcement capture and C2 (drafted with help from Claude in a separate chat)</summary>

```text
Approved: the two CI files as written. Next, in this order:

Capture the server-enforcement evidence with a throwaway script (outside the committed code, or clearly marked as evidence tooling): start the backend on a free port, create a throwaway member and a throwaway admin with random passwords that you never print, log or save, and never read my .env. Send six requests to POST /api/ml/v1/no-show/predict/ over real HTTP with a CSRF-enforcing client and print label, status and JSON body for each: (1) valid body as the member → 200; (2) lead_time_days 91 → 400; (3) extra field role: 'admin' → 400 ‘Unknown field.’; (4) member without the CSRF header → 403; (5) signed out → 401; (6) admin session → 401. Use the Swagger example body. Delete the throwaway accounts and stop the server afterwards and confirm with netstat. If any status differs from what I expect, say so instead of adjusting it.
Prepare C2 (docs only) and SHOW ME the diff before committing: the README paragraph on the 0.22 cutoff (use the numbers from the model report), the new caption for card-result.png, the test counts (429 backend), and docs/evidence/week3.md sections for ‘Server enforcement (mentor review)’ with the six results, labelled clearly as captured by a script over real HTTP, not in the browser, and saying the wrong-role case is 401, not 403. Also link the prompt refinement (Week 2 prompt 12) and the test that failed before the fix with its saved failing output, using links to a commit that is already pushed (5f3a820) and checking the line anchors against that commit.
Log this message as the next prompt, marked ‘drafted with help from Claude in a separate chat’.

Commit C2 and then C3 (only the two .github files) only after I approve your report. Don’t push.
```
</details>

<details><summary>31. C2 and C3 approval (drafted with help from Claude in a separate chat)</summary>

```text
Approved. Two changes before you commit: (1) change the README’s backend test time to ‘about 2–4 minutes’; (2) copy the capture script into the repo as docs/evidence/capture_enforcement.py (confirm that it contains no passwords, tokens or .env access), and mention it in the ‘Server enforcement’ section of docs/evidence/week3.md with its path. Log this message as prompt 31, marked ‘drafted with help from Claude in a separate chat’. Then commit C2 and C3 as proposed, and show me git log --oneline -4, git status and the full hashes. Do not push.
```
</details>

<details><summary>32. Push request (drafted with help from Claude in a separate chat)</summary>

```text
Push feature/week3-ml-pipeline now (no force) and show me the push output and git status
```
</details>

<details><summary>33. C4: race-test evidence on the Week 3 head (drafted with help from Claude in a separate chat)</summary>

```text
The first CI run on 4711574 is green: https://github.com/mominaasif-45/healthprofile/actions/runs/42509900392/job/128820476023 .Please do the C4 step: on that exact commit with a clean tree, run the section 5 evidence commands (git status, the tested commit line, the database vendor and server version, and python -m pytest tests/test_concurrency.py -rs -vv) and show me the real output. Then draft C4 (docs only): add that output and the Actions run link to docs/evidence/week3.md, log this message as the next prompt marked ‘drafted with help from Claude in a separate chat’, and show me git diff --stat. Don’t commit until I approve. Don’t push.
```
</details>

<details><summary>34. C4 approval and push (drafted with help from Claude in a separate chat)</summary>

```text
Approved. Keep prompt 32 and add the label ‘drafted with help from Claude in a separate chat’ to it. Log this message as prompt 34 with the same label. Commit C4 with the message you proposed (adjust the prompt numbers in it to 32-34), then push feature/week3-ml-pipeline (no force). Show me the push output, git status, git log --oneline -3 and the full hash of the final head.
```
</details>

### My decisions and corrections

| Phase | Options I was given | What I decided or added |
|---|---|---|
| 0 Plan | New dependencies; who may call the endpoint; commits vs `CLAUDE.md`'s "do not commit"; files outside the new `ml/` app; committing the data and model; card placement | Approved scikit-learn, numpy, pandas, joblib with exact pins and no matplotlib / Jupyter; members only, throttled; one commit per phase after my approval, never push; approved the file list; commit data and model, **with a SHA-256 check before loading the pickle** and a README explanation (my addition); card on `/profile` below the wellness card; added an adjustable noise level and per-group metrics |
| 1 Data | Columns, blank rates, default noise as proposed; after the run: keep noise 1.0 (ceiling 0.657 ROC-AUC) or strengthen the rule | Approved; added: the data card must say the group differences in the rule are arbitrary and not claims about real people, and the "best possible score" must be explained in plain words. After the report: **kept noise at 1.0** |
| 2 Split and analysis | 70 / 15 / 15 stratified split; median + "was blank" column for numbers, `missing` category for blanks; `hour` as a category; analysis on the training pile only | Approved as proposed; asked again for tests first with fail-then-pass proof |
| 3 Models | Threshold: best F1 or "at least 60% recall, best precision"; an extra model without `age_band` | **Best F1**; **skipped** the `age_band` experiment (README future work, Phase 7). **Changed the leakage alarm**: the plan alarmed at the pile's ceiling itself. The idea of a margin (an honest model can beat a ceiling measured on the same finite pile by luck, so alarm only above the ceiling **+ 0.03** or above 0.90) was **suggested by Claude in the separate chat**; I reviewed and approved it, and asked for the margin to be explained in the report. Asked for the slow retraining test to be skippable with a flag but run by default |
| 4 Artifact | Add `.gitattributes` (`*.joblib binary`, outside the approved file list); ship the model fitted on training rows only, or refit on training + validation | Approved `.gitattributes`; **training rows only**, so the shipped file is exactly the one the report describes; added: the README must say a production system would refit on all the data and re-derive the threshold |
| 5 Endpoint | Members with no profile or a deactivated profile: allow, or refuse with 403; the throttle rate | **Allowed** (the endpoint never touches profile data); **30 requests per minute per member** |
| 6 Dashboard card | Hide the card when there is no profile, or show it under "Create your profile"; add a side-menu link | **Hidden without a profile**, noted in the README as a design choice (Phase 7); **side-menu link added**; asked for manual browser steps (normal case, a 400, keyboard only, both themes, 429 and 503) |
| 7 README and handoff | README outline; screenshots; validation list and how to name the tested commit; a Week 3 PR and its base | Approved the outline; took the screenshots myself (three new ones); confirmed PR #3's base is `main` on GitHub; **approved a stacked Week 3 PR on top of the Week 2 branch, but not opened until I have seen the final validation**; asked for a backup push first, an empty "My reflection" heading for me to write, and a marked placeholder for my Loom link |

### What the checks caught

- **Phase 1, dependencies.** Installing the four approved packages also brought in `scipy`, `threadpoolctl`, `narwhals`
  (required by scikit-learn) and `cloudpickle` (required by joblib). All are pinned, and `requirements.txt` was compared
  line by line with `pip freeze`.
- **Phase 1, line endings.** This machine has `core.autocrlf=true`, so git may check the CSV out with Windows line
  endings. A checksum of the raw bytes would then stop matching. The dataset checksum is taken over the text with line
  endings normalised, and a test proves CRLF and LF give the same checksum.
- **Phase 1, the noise ceiling.** The best possible ROC-AUC at noise 0 (0.671) and 0.5 (0.672) are within measurement
  wobble, so the test checks only the clear trend (0 > 1 > 3), and the data card says so.
- **Phase 2, tests that had never failed.** All 13 new tests passed on their first run, which proves little on its own. So
  Claude Code broke the code on purpose twice: making the analysis read the whole file instead of the training pile
  (3 tests failed), and letting a feature (lead time) influence the split (2 tests failed). The original code was then
  restored and all 13 passed again.
- **Phase 2, a wrong table order.** Reading the generated report showed the no-show-rate tables in a jumbled order (the
  grouping followed row order, not category order). The numbers were right; the order was fixed, and the "committed
  report matches the script" test caught the stale file until it was regenerated.
- **Phase 3, rules checked by breaking them.** Three deliberate breaks were each caught by a test: choosing gradient
  boosting whenever its interval merely reached above zero, removing the 0.03 leakage margin, and sending threshold
  ties to the lower threshold. A planted copy of the answer (`reminder_sent` = "yes" exactly for no-shows) stops the
  experiment with `LeakageAlarm`.
- **Phase 3, the complex model did not earn its place.** Gradient boosting's validation PR-AUC advantage over logistic
  regression was +0.016 with a 95% interval of -0.013 to +0.045, so by the rule fixed in advance logistic regression
  was chosen. Gradient boosting also memorised more (train-validation ROC-AUC gap +0.087 vs +0.045).
- **Phase 3, wording checked against the numbers.** Reading the generated report showed a few fixed sentences that
  would silently become wrong if the data changed (for example "the confident false alarms are mostly long waits
  without reminders"); they are now computed from the results, and two claims were softened ("nothing in the
  columns tells them apart" became "little").
- **Phase 3, speed.** The full experiment takes about 40 seconds; `ML_SKIP_SLOW=1` skips the 5 tests that need it
  (they run by default).
- **Phase 4, byte-identity.** A second, independent `python -m ml.train --check` run rebuilt the model with the same
  SHA-256 (`d69f7723…`), a largest probability difference of 0.0 and identical metadata. Byte-identity is reported
  but not required by the tests, because a pickle may store the same model differently on another platform.
- **Phase 4, the checks checked.** Three deliberate breaks were each caught: unpickling before the checksum
  comparison (the `joblib.load` trap fired), skipping the scikit-learn version check, and a `--check` that always
  reported matching predictions.
- **Phase 4, the human step.** After the first training run, the new checksum was pasted into `EXPECTED_SHA256` in
  `ml/artifact.py`; this is the reviewed code change that accepts a model file. I checked that line myself against
  PowerShell's `Get-FileHash` on the `.joblib` file, and it matches.
- **Phase 5, failing for the right reason.** Before the route existed, all 68 new tests failed because of it: the 404
  "Not Found" page, plus three that could not find `ml.views`, `ml.predictor` or the schema path. To make them fail
  with 404 rather than stop at import, the test file imports the new modules only inside the tests that need them.
- **Phase 5, the checks checked.** Four deliberate breaks were each caught: ignoring unknown fields instead of
  rejecting them, removing the strict whole-number check (2 tests failed: `"21"` and `21.0`, the two values plain DRF
  quietly accepts), logging the inputs in the view, and removing the throttle.
- **Phase 5, a Swagger warning.** The new `age_band` field has the same six values as the profile's `age_range`, so
  drf-spectacular warned about one choice set with two names. Fixed with one `ENUM_NAME_OVERRIDES` entry that keeps
  the existing name `AgeRangeEnum`; the schema now builds with no warnings.
- **Phase 5, real examples only.** The Swagger response examples are real outputs of `noshow-1.0.0`; a test sends each
  example request and checks the response matches exactly.
- **Phase 6, failing first.** Before the card existed, the new test file could not even import it ("Failed to resolve
  import @/components/profile/NoShowDemoCard"); after writing it, all 23 tests passed.
- **Phase 6, the checks checked.** Four deliberate breaks were each caught: sending "Not recorded" as an empty string
  instead of `null` (2 tests failed), keeping a stale result after a field changed, removing `aria-live` from the
  result area, and dropping the 429 message.
- **Phase 6, rounding.** The card rounds percentages through whole basis points as a precaution against floating-point
  surprises, and a test covers 0.0505 → "5.1%". When checked in Node, plain rounding also gave 5.1% for this value, so
  this is a safeguard, not a bug that was found.
- **Phase 6, lint.** The first lint run flagged one unused import in the new test file; removed.
- **Phase 6, my manual check.** Before approving the commit, I tried the card by hand in the browser with both servers
  running: the normal case, the "91 days" check, the keyboard-only path, and light and dark themes. All worked.
- **Phase 7, screenshot names.** My Phase 7 message gave two wrong file names (`swagger-week3-request.png` and
  `swagger-week3-responses.png`). A `dir` check found the real names, `swagger-request.png` and
  `swagger-responses.png`; no file was renamed. I then corrected my message (prompt 18), a second `dir` confirmed all
  five `.png` files, and the README uses the real names.
- **Phase 7, final validation.** The final validation results are in
  [docs/evidence/week3.md](evidence/week3.md); the tested commit is named only after the full list passed on it.

### Tools (Week 3)

| Tool | What I used it for |
|---|---|
| **Claude (chat, separate)** | Drafting every prompt I sent in this session (each marked above), and suggesting the 0.03 leakage margin, which I reviewed and approved |
| **Claude Code** (in the repo) | Reading the code, writing each phase plan, writing tests first, implementing, deliberately breaking code to prove the tests catch it, running every check, and committing each phase after my approval |
| **My own checks** | `Get-FileHash` on the model file against `EXPECTED_SHA256`; trying the card by hand (normal case, the 91-days check, keyboard only, light and dark); confirming PR #3's base on GitHub; taking the screenshots |

### Limits (stated honestly, Week 3)

- **Synthetic data follows rules we wrote.** The models rediscover those rules; the metrics show the method working
  and say nothing about real clinics or real people. The group differences in the rule are arbitrary.
- **One split, one seed, 900-row validation and test piles.** The intervals in the model report show how much the
  numbers could move; small groups (65+ and over 30 km on the test rows) are too small to judge, and in person is
  only just above the limit.
- **The shipped model is fitted on the training rows only**; a production system would refit on all the data and
  re-derive the threshold.
- **A `.joblib` file is a pickle.** The SHA-256 check proves the file is the one we built and reviewed; it does not make
  an untrusted pickle safe. Safer formats (skops, ONNX) would need new dependencies.
- **Not tried:** training without `age_band` to measure what removing a group input costs (left as future work).

### My reflection
**1. What did you learn about building an ML pipeline?**

I learned that data should be split into training, validation, and testing sets before analyzing it. Data leakage can give misleading results because the model gets information it should not have. I also learned that accuracy is not always reliable, especially when the data is imbalanced. Choosing the right threshold helps balance precision and recall.

**2. What did the AI get wrong or suggest, and how did you or the tests catch it?**

Claude suggested using a 0.03 margin for the data leakage alarm. I reviewed the suggestion, approved it, and added it to the project log. The tests also used a planted copy of the answer to check whether the leakage alarm could detect it. This taught me that AI suggestions should be checked and tested before being accepted.

**3. What would you do differently next time?**

Next time, I would try training the model without the age band feature to see how much it affects the results. I would also compare the models more carefully and spend more time understanding the evaluation results before choosing the final model.

**4. What still confuses you?**

I still find it a little confusing how to choose the best threshold and balance precision and recall. In my project, the model had 29.5% precision and 50.8% recall at a threshold of 0.22. I learned that lowering the threshold catches more missed appointments but can also create more wrong predictions. I also want to understand better how to decide which ML model is best for a problem.



## Week 4: Comparative ML Workbench, Clustering, LLM Endpoint and FAQ Assistant

Week 4 extends the Week 3 ML system into a comparative workbench (supervised and unsupervised), adds an LLM backend
endpoint and an educational FAQ assistant over approved fictional clinic policies, and shows all three in a dashboard.
It is planned in a separate git worktree on `feature/week4-ml-llm-rag`, started from the `feature/week3-ml-pipeline`
head (PR #4 still under review), with its own database `healthprofile_week4`.

### Who did what

- **My prompts and my phase decisions** (each marked below) were drafted with help from Claude in a separate chat.
  They are not written by me alone. I make the decisions in them and approve every phase with "go".
- **Claude Code** works in the repository: it reads the code, writes each plan, writes the tests first, implements and
  runs the checks. It does not read `.env`, merge or push.

### Prompt history (as sent in the session)

<details><summary>1. Week 4 planning request (drafted with help from Claude in a separate chat)</summary>

```text
New task: Week 4. The brief (Elevate Engine Weeks 4 to 6, Week 4 section) asks to: extend the Week 3 ML system into a comparative workbench (Logistic Regression, Random Forest and one gradient boosting model or SVM; confusion matrix, precision, recall, F1, ROC-AUC, PR-AUC, train versus validation, stratified cross-validation, one tuned model with GridSearchCV or RandomizedSearchCV, permutation importance, false positive and negative inspection, reproducible preprocessing pipeline); unsupervised learning (K-Means plus DBSCAN or Agglomerative on non-sensitive engagement features, silhouette and elbow, PCA 2D plot, explanation that clusters are exploratory); an LLM backend endpoint (system prompt, task prompt, context window strategy, token limit, temperature, JSON response schema); an educational FAQ assistant over approved fictional clinic policies (upload, text extraction, chunking, embeddings, vector search, cited passages, explicit ‘insufficient information’); a dashboard with three tabs (supervised, clusters, LLM Q&A) showing model versions, metrics and disclaimers; 12 LLM evaluation prompts (answerable, ambiguous, out-of-scope, prompt-injection) comparing two prompts or retrieval settings. Constraints: train-only fitting, pinned dependencies and seeds, no patient-identifiable data to external LLMs, validate upload types and sizes, enforce upload permissions, treat retrieved documents as untrusted, rate limits, timeouts, safe errors, approximate token and cost reporting, never present output as diagnosis; keep Weeks 1 to 3 working with regression evidence.

Plan only. Change nothing and do not read or print .env. Please propose:

A new git worktree and branch feature/week4-ml-llm-rag from the current feature/week3-ml-pipeline head, in C:\Users\Momina\Projects\healthprofile-week4, with its own database healthprofile_week4 (owner healthprofile_user, like Week 3), its own venv on Python 3.13, its own .env made by copying values without printing them, and its own admin account. Say how the stacked PR will work (base feature/week3-ml-pipeline) and how this avoids touching PR #3 and PR #4.
Which parts of the Week 3 ML package we reuse, and what new files each phase adds.
For the LLM and RAG: options for the LLM provider (hosted API or local), embeddings, and vector storage, with the privacy, cost, install size and testability of each, and your recommendation. Use a fake LLM and fake embeddings in tests so no network is needed. Explain how the API key will be kept out of git, logs and screenshots.
The phases (supervised, unsupervised, LLM endpoint, RAG, 12-prompt evaluation, dashboard, README and evidence), with what each must prove, and what we should cut or simplify to finish by Tuesday 11:59 PM PKT, ordered by the acceptance checks.
The regression evidence plan for Weeks 1 to 3.
What I should decide myself.

Start a Week 4 section in docs/ai-workflow.md and log this message as prompt 1, marked ‘drafted with help from Claude in a separate chat’. Don’t commit and don’t push.
```
</details>

<details><summary>3. Setup go, with my answers to the planning questions (drafted with help from Claude in a separate chat)</summary>

```text
Go for setup, with these answers. (1) Tuesday 10 Nov, 11:59 PM PKT: apply every cut. (2) Provider: LOCAL Ollama for the chat model and for embeddings (nomic-embed-text), no key, LLM_PROVIDER=fake|ollama using Python’s built-in urllib. Measure the real response time on my laptop and set a realistic timeout (the first call loads the model) with a clear loading state in the UI. Cost shows as 0.00 (local) with real token counts. (3) No new packages at all (no anthropic, no pypdf). (4) One commit per phase after I approve. (5) The edits outside the new app in your list are approved. (6) Reject questions that contain a phone number or email. (7) Admins upload, members ask. (8) Keep noshow-1.0.0. (9) Compare two system prompts. (10) You draft 3 or 4 fictional policies and I review and approve them. (11) Do NOT commit anything on the week3 branch. Move the Week 4 section of docs/ai-workflow.md into the new worktree and leave prompt 35 uncommitted in week3. Phase order: 1, 2 (minimal), 3, 4, 5, 6, 7.

Now: create the worktree and branch, and do the setup in your section 1. Run what you can. For anything that needs my password or my hands (psql password, the .env copy), stop and give me the exact lines to type, one at a time, saying which terminal and folder. Never read or print .env. After the setup works, record the baseline test counts, then show me the Phase 1 plan only and wait for my ‘go’. Log this message as prompt 3, marked ‘drafted with help from Claude in a separate chat’. Don’t commit and don’t push.
```
</details>

<details><summary>4. Setup done on my side, Ollama installed (drafted with help from Claude in a separate chat)</summary>

```text
Done: I ran the psql line (CREATE DATABASE) and the two .env lines. Also, Ollama is installed (0.40.15) with nomic-embed-text and llama3.2:3b pulled, and the test run worked. My laptop has 15.9 GB RAM and about 13 GB is usually in use while Chrome and VS Code are open, so keep memory use in mind. Please continue: check the database name without showing any secret, run migrate, give me the exact create_admin line, record the baseline counts, and then show me the Phase 1 plan only. Log this message as the next prompt, marked ‘drafted with help from Claude in a separate chat’. Don’t commit and don’t push.
```
</details>

<details><summary>5. Phase 1 go, with three additions (drafted with help from Claude in a separate chat)</summary>

```text
I created the admin. Go for Phase 1 as planned, with three additions. (a) The baseline lists the build as ‘10 pages’, but Week 3 showed ‘Generating static pages (11/11)’: please explain or correct it. (b) The test pile was already used in Week 3 for the baseline, logistic regression and gradient boosting. In Week 4 the model comparison and any choice must be made on validation only, and the test numbers (including random forest) are reported afterwards, not used to choose. Say this plainly in the workbench report and in the README limitations. (c) Keep memory low (n_jobs=1) and report peak memory. Tests first, shown failing and then passing, then the three break-it checks, then the full validation list, with real outputs. Don’t commit until I approve. Don’t push. Log this message as the next prompt, marked ‘drafted with help from Claude in a separate chat’.
```
</details>

<details><summary>6. Phase 1 approved, Phase 2 plan request (drafted with help from Claude in a separate chat)</summary>

```text
Approved. Commit Phase 1 as proposed. Log this message as prompt 6, marked ‘drafted with help from Claude in a separate chat’, and include it in the same commit. Then show me git log --oneline -3 and git status. Then show me the Phase 2 plan only (the minimal clusters version): engagement features only (no age band, distance band, or the no-show label), scaler, PCA and K-Means fitted on the training rows only, elbow (k=2 to 8) and silhouette, Agglomerative at the chosen k compared with K-Means, 2D PCA points for the plot, a cluster summary with plain-words descriptions that never call clusters patient types or risk groups, a section saying why clusters are exploratory, a read-only member endpoint like the workbench one, tests first, break-it checks, and the regression checks. Keep it as small as it can be and still meet the brief. Don’t push.
```
</details>
