# AI-Assisted Development Workflow

> How I used AI to plan, build, review and debug HealthProfile.
> Items marked **[CONFIRM]** must be checked or rewritten in my own words before submitting.

## 1. Tools I used and why

| Tool | What I used it for |
|---|---|
| **Claude (chat)** | Understanding the brief, planning the architecture and database, writing `docs/PLAN.md`, choosing the UI theme, step-by-step guidance for the first backend pieces (User model, signup, JWT login), reviewing code and debugging |
| **Claude Code** (AI coding agent in my repo) | Generating the larger parts: profiles API, admin session API, management commands, the test suite and the Next.js frontend **[CONFIRM: list exactly what Claude Code generated]** |
| **Swagger UI** (`/api/docs/`) | Manually testing every endpoint and checking real status codes and cookies |
| **Browser DevTools** | Verifying `access` / `refresh` / `sessionid` cookies are `HttpOnly` and `SameSite=Lax` |

## 2. Context management

- I wrote the plan first (`docs/PLAN.md`: architecture, tables, endpoints, tests) and gave it to the AI as the single source of truth, instead of re-explaining the project in every prompt.
- I worked **one phase at a time** (1 foundation + user auth, 2 profiles, 3 admin, 4 frontend, 5 docs), starting a **fresh chat per phase** so old context didn't leak in or waste tokens.
- I attached only the files a phase needed, not the whole repo.
- **[CONFIRM: any other context tricks you used, e.g. a rules file, CLAUDE.md, or pasting only error output]**

## 3. Prompt iterations

### Iteration 1: first, naive prompt

```text
Build a Django app with user signup, JWT login and admin login for a health profile project.
```

**Result / problems observed:** **[CONFIRM: what you actually saw. Typical problems:]**
- JWT and session logic mixed together; admin and user shared one login endpoint.
- Tokens returned in the JSON body (would end up in `localStorage`, exposed to XSS).
- No CSRF handling, no `.env`, AI edited many unrelated files at once.

### Iteration 2: structured, scoped prompt

I rewrote the prompt using a fixed structure (saved in `docs/prompts/master-prompt-v2.md`):

```text
ROLE: Senior full-stack engineer in this repository
GOAL: Complete CURRENT PHASE so every acceptance item passes and pytest is green
CURRENT PHASE: 1
CONTEXT: docs/PLAN.md is the source of truth; stack; user auth = JWT in HttpOnly cookies;
         admin auth = Django sessions; every view sets authentication_classes explicitly
IN SCOPE: only the files of the current phase (listed per phase)
OUT OF SCOPE: other files, applied migrations, new dependencies, tokens in localStorage,
              public admin signup, accepting "role" from request bodies
ACCEPTANCE: observable behaviours + tests (401/403/409 cases, CSRF, expiry, blacklisting)
PROCESS: Inspect -> plan -> STOP for my "go" -> implement -> validate
OUTPUT: changed files, tests run, risks, unknowns, commit message
```

### What changed between the two

| | Iteration 1 | Iteration 2 |
|---|---|---|
| Auth design | Mixed / guessed | User JWT and admin session explicitly separated |
| Files touched | Many, unpredictable | Only the phase's listed files |
| Security | Tokens in body, no CSRF | HttpOnly cookies, CSRF on writes, role from DB |
| Review effort | Hard to review one big diff | Small diffs, a plan to approve first |
| Tests | None | Required by the acceptance list |

## 4. Controlling the blast radius

- Each phase's prompt listed the **only** files the AI could change, plus an explicit OUT OF SCOPE list.
- The AI had to **show a plan and stop** before writing code; I approved it with "go".
- Before every commit I ran `git diff --stat` to confirm only expected files changed. **[CONFIRM]**
- One feature branch (`feature/phase1-user-auth`), small commits, merged to `main` by pull request.
- `python manage.py check` and `pytest` after every AI change, so a regression shows up immediately.

## 5. Manual security review of the AI's code

I read these parts myself and checked them against the brief:

| Check | Where | Result |
|---|---|---|
| Passwords stored only as hashes | `accounts/models.py` (`set_password`), test `test_valid_signup_creates_user_with_hashed_password` | ✅ |
| Signup can't create admins (`role`, `is_staff` ignored) | `SignupSerializer` accepts only 3 fields; test `test_role_in_body_is_ignored` | ✅ |
| JWT has no secrets (only `user_id`, `exp`, `jti`, `token_type`) | `RefreshToken.for_user` | ✅ |
| Tokens in HttpOnly cookies, not the response body | `accounts/cookies.py`; DevTools screenshot | ✅ |
| User views accept only JWT; admin views only session + `IsAdminRole` | `authentication_classes` on every view; `DEFAULT_AUTHENTICATION_CLASSES = []` | ✅ |
| Role always read from the database, never from the browser | `IsAdminRole`, `CookieJWTAuthentication` | ✅ |
| No IDOR: users have no `/profiles/{id}/` route | `profiles/urls.py`; test `test_user_only_sees_own_profile_and_no_route_to_others` | ✅ |
| CSRF on every state-changing cookie request | `enforce_csrf`, `SessionAuthentication`; CSRF tests | ✅ |
| Secrets only in `.env`; `.env` git-ignored; `.env.example` committed | `.gitignore`, `git check-ignore -v .env` | ✅ |
| Login brute-force throttled (5/min) | `ScopedRateThrottle`; test `test_login_is_throttled_after_five_attempts` | ✅ |

**Things I changed or questioned after review:** **[CONFIRM / add your own]**
- README claimed Django rotates the CSRF token at *every* login; corrected: only the admin (session) login rotates it.
- The `(status, created_at)` index only helps when the admin filters by status; I documented that instead of overselling it.

## 6. Bug story: an unexpected AI-generated change

**Symptom.** `POST /api/auth/user/logout/` returned **403 "CSRF failed"** in Swagger, even after I pasted a fresh CSRF token.

**How I isolated it.**
1. `GET /api/auth/me/` worked, so the JWT cookie was fine. The problem was only on POST.
2. In Swagger's **Curl** box I saw an `X-CSRFTOKEN` header that I had not typed: Swagger (drf-spectacular) already adds it automatically from the `csrftoken` cookie.
3. The AI-generated view had **also** declared a manual `X-CSRFToken` header parameter. I filled it in, so the request carried the header **twice**; the browser merged both values and Django saw an invalid token.

**Fix.** Removed the extra `X-CSRFToken` parameter from the refresh and logout views (`accounts/views.py`). Swagger's automatic header is enough, and the frontend sends it from `lib/api.ts`.

**Regression tests.** `test_refresh_after_logout_returns_401` (logout returns 204) and `test_user_post_without_csrf_token_is_rejected` (403 without the header, success with it) now run in `pytest`.

**Side discovery.** A later `GET /me` returned 401 because more than 15 minutes had passed: the access token had expired. This confirmed expiry works and is now covered by `test_expired_access_token_returns_401`.

## 7. Verification

- `python manage.py check`: no issues
- `python -m pytest`: **[CONFIRM: e.g. 51 passed]**
- `npm run lint` and `npm run build`: **[CONFIRM: no errors]**
- Manual click-through of every page in light and dark mode **[CONFIRM]**
- EXPLAIN plan for the admin list query (see README) uses `profile_status_created_idx` **[CONFIRM]**

## 8. What I'd do differently next time

- Write the acceptance tests (or at least the test list) **before** asking the AI to implement a phase.
- Keep a prompt log from the very first minute instead of reconstructing it.
- Commit after every small working step, not after a large batch.
- **[CONFIRM: add one thing in your own words]**
