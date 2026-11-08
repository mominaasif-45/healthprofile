# Week 3 evidence: final validation and real outputs

> Educational demo on synthetic data. Not medical advice, not a diagnosis.

This file records real command output for the Week 3 ML pipeline and prediction API
(branch `feature/week3-ml-pipeline`, started from `feature/week2-profiles-audit` at `96e29a2`).

## Which commit was tested

A file cannot contain the hash of the commit that adds it, so:

* The **code** last changed in `493a2d1` (Phase 6). The Phase 7 commit that adds this file changes only
  documentation (`README.md`, `docs/ai-workflow.md`, `docs/ml/data-card.md`, this file) and screenshots.
* The outputs below are from the run on 2 November 2026, before the Phase 7 commit: the working tree had **no code
  changes** against `493a2d1` (step 1), only the documentation and screenshots.
* After the Phase 7 commit, the **same list is run again on that exact commit with a clean working tree**. Only if it
  passes is that commit's hash named as the **tested commit**, in the pull request description.
* **Update (4 November 2026):** the Week 2 contact deletion race fix was merged into this branch afterwards, and the
  whole list was run again on **the merge commit**. Those results are the current ones: see
  [After the Week 2 race fix](#after-the-week-2-race-fix) at the end of this file. The outputs below are kept as the
  record of the earlier run.
* **Update (8 November 2026):** the PostgreSQL race tests now run in CI, and were run on the Week 3 head `4711574`
  with a clean tree: see
  [PostgreSQL race tests in CI and on the Week 3 head](#postgresql-race-tests-in-ci-and-on-the-week-3-head-mentor-review-of-pr-3).

## Final validation list

Run from `backend/` (venv active) and `frontend/`, with `ML_SKIP_SLOW` **not** set.

| # | Check | Result |
|---|---|---|
| 1 | No code changes against `493a2d1` (`git diff --stat HEAD -- backend frontend`) | empty |
| 2 | `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| 3 | `python manage.py check` | `System check identified no issues (0 silenced).` |
| 4 | `python manage.py spectacular --validate` | no warning or error summary printed (0 warnings, 0 errors) |
| 5 | `python -m pytest` (full) | `424 passed in 124.12s (0:02:04)` |
| 6 | `python -m ml.train --check` | predictions, labels, metadata **and bytes** identical (output below) |
| 7 | Rebuild the dataset, analysis and model report, then `git diff --exit-code` | no changes (exit 0) |
| 8 | `npm test` | `Test Files 6 passed (6)`, `Tests 47 passed (47)` |
| 9 | `npm run lint` | exit 0, no problems reported |
| 10 | `npm run build` | `✓ Compiled successfully`, `Finished TypeScript`, `✓ Generating static pages (11/11)` |

### Step 6: the model is reproduced

```
predictions_identical: True
max_probability_difference: 0.0
labels_identical: True
metadata_identical: True
bytes_identical: True
rebuilt_sha256: d69f7723b34fe773da3eb09841304a050bb72410654c00487b1a4f242fec8218
committed_sha256: d69f7723b34fe773da3eb09841304a050bb72410654c00487b1a4f242fec8218
ok: True
OK: the committed artifact is reproduced.
```

The tests require identical predictions, labels and metadata. Identical bytes are reported but not required: a
pickle may store the same model in different bytes on another platform.

### Step 7: the committed data and reports come from the code

```
Wrote ...\backend\ml\data\appointments.csv (6000 rows, no-show rate 20.8%, best possible ROC-AUC 0.6568)
Wrote ...\docs\ml\eda.md
Wrote ...\backend\ml\reports\metrics.json and ...\docs\ml\model-report.md (chosen: logistic_regression)
git diff --exit-code: no changes (exit 0)
```

(git also printed "LF will be replaced by CRLF" notes for these files: that is the `core.autocrlf` setting, and the
dataset checksum ignores line endings on purpose.)

## Real request and response

Captured from the real endpoint (Django test client, throwaway test database): a member signed in, fetched a CSRF
token and posted one fictional appointment.

```
=== Request: POST /api/ml/v1/no-show/predict/ (member JWT cookie + X-CSRFToken header)
{"lead_time_days": 21, "weekday": "mon", "hour": 9, "visit_type": "new_visit",
 "booking_channel": "online", "reminder_sent": "no", "prior_visits": 3,
 "prior_no_shows": 1, "distance_band": "15_30km", "age_band": null}

=== Response: HTTP 200
{"prediction": "likely_no_show", "probability": 0.5279, "threshold": 0.22,
 "model_version": "noshow-1.0.0",
 "disclaimer": "Educational demo trained on synthetic data. Not medical advice, not a diagnosis, and not a prediction about any real person or appointment."}

=== Rejected request (lead_time_days 120, weekday "sunday", hour missing, extra no_show): HTTP 400
{"error": {"code": "validation_error", "message": "Invalid input.",
  "fields": {"lead_time_days": ["Must be between 0 and 90."],
             "weekday": ["Must be one of: mon, tue, wed, thu, fri, sat."],
             "hour": ["This field is required."],
             "no_show": ["Unknown field."]},
  "request_id": "85e97f94-ce8f-4095-a240-3e63c548267c"}}
```

## Tests that were proved to fail first

Every Week 3 test file was written before the code it tests and shown failing for the right reason, then passing.
Each phase also broke its own code on purpose to check that the tests catch it (details in
[docs/ai-workflow.md](../ai-workflow.md), "What the checks caught").

| Phase | Before the code existed | After | Deliberate breaks caught |
|---|---|---|---|
| 1 Data | `ModuleNotFoundError: No module named 'ml'` | 38 passed | |
| 2 Split | `ImportError: cannot import name 'analysis'` | 13 passed | analysis reading all rows; a feature influencing the split |
| 3 Models | `ImportError: cannot import name 'evaluate'` | 17 passed | selection rule, leakage margin, threshold ties |
| 4 Artifact | `ImportError: cannot import name 'artifact'` | 13 passed | unpickling before the checksum, version check, `--check` |
| 5 API | all 68 failed on the missing route (404) | 68 passed | unknown fields ignored, loose integers, logging inputs, no throttle |
| 6 Card | the card component did not exist | 23 passed | blank sent as `""`, stale result kept, no `aria-live`, no 429 message |

## Checked by hand

* `EXPECTED_SHA256` in `backend/ml/artifact.py` compared with PowerShell `Get-FileHash` on the model file: matches.
* The dashboard card in the browser with both servers running: the normal case, the "91 days" quick check, the
  keyboard-only path, and light and dark themes.

## After the Week 2 race fix

The PR #4 review asked for the inherited Week 2 contact deletion race to be fixed before the stack is merged.
The fix (`dbe41db` on `feature/week2-profiles-audit`) was brought into this branch with a **merge, not a rebase**.
Only `README.md` conflicted (two test-count lines); both sides were kept. No Week 3 code changed.

The full list was run again on **the merge commit**, with a clean working tree and `ML_SKIP_SLOW` not set,
on 4 November 2026. The commit that adds this section changes only documentation.

| # | Check | Result |
|---|---|---|
| 1 | `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| 2 | `python manage.py check` | `System check identified no issues (0 silenced).` |
| 3 | `python manage.py spectacular --validate` | no warnings or errors (exit 0) |
| 4 | `python -m pytest` (full) | `427 passed in 108.61s (0:01:48)` (278 Week 1–2 + 149 Week 3) |
| 5 | `python -m ml.train --check` | predictions, labels, metadata and bytes identical; `OK: the committed artifact is reproduced.` |
| 6 | Rebuild the dataset, analysis and model report, then `git diff --exit-code` | no changes (exit 0) |
| 7 | `npm test` | `Test Files 6 passed (6)`, `Tests 47 passed (47)` |
| 8 | `npm run lint` | exit 0, no problems reported |
| 9 | `npm run build` | `✓ Compiled successfully`, `✓ Generating static pages (11/11)` |

## Server enforcement (mentor review)

The PR #4 review asked for proof that the **server** enforces the rules, because the card's own range check alone
cannot show that. These six responses were **captured by a script over real HTTP, not in the browser**, on
8 November 2026:

* `python manage.py runserver` on `http://127.0.0.1:53028`, with the code of `a1e96ce` (no code changes in the
  working tree).
* A throwaway member (made with `create_user`) and a throwaway admin (made with `manage.py create_admin`), both with
  random passwords that were never printed, logged or saved.
* The client used real cookies: it fetched `/api/csrf/`, signed in through `/api/auth/user/login/` or
  `/api/admin/login/`, and sent the `X-CSRFToken` header except in case 4.
* Every request is `POST /api/ml/v1/no-show/predict/` with the Swagger example body "Fictional appointment (likely
  no-show)", changed only where the label says.
* The script is [`docs/evidence/capture_enforcement.py`](capture_enforcement.py) (evidence tooling, not part of the
  app). It contains no passwords, tokens or secrets and never opens `backend/.env`. Run it from the repository root
  with the backend venv active: `python docs/evidence/capture_enforcement.py`. The copy in the repo differs from the
  one that ran in two places only: it finds `backend/` from its own location instead of a fixed path on my computer,
  and the wording of its cleanup line is corrected.

Afterwards both accounts were signed out and deleted (0 left), and the server was stopped. `netstat -ano` then showed
no listener on port 53028, only closed connections in `TIME_WAIT`. The audit log is append-only, so the admin's
sign-in and sign-out rows (`admin.login`, `admin.logout`) remain, with the actor now empty. They contain no values.

| # | Request | Expected | Real |
|---|---|---|---|
| 1 | Valid example, signed-in member | 200 | **200** |
| 2 | `lead_time_days: 91`, member | 400 | **400** |
| 3 | Extra field `role: "admin"`, member | 400 "Unknown field." | **400** "Unknown field." |
| 4 | Member, no `X-CSRFToken` header | 403 | **403** |
| 5 | Signed out (CSRF cookie and header, no sign-in) | 401 | **401** |
| 6 | Admin session (`sessionid` cookie and `X-CSRFToken`) | 401 | **401** |

**The wrong-role case is 401, not 403.** This endpoint accepts only the member JWT cookie. An admin's session cookie
is not a credential here at all, so the server treats the admin as not signed in (401), the same as on every member
route. 403 is used only when a signed-in member leaves out the CSRF header (case 4).

```text
=== (1 valid Swagger example, member) expected 200, got HTTP 200: as expected
{"prediction": "likely_no_show", "probability": 0.5279, "threshold": 0.22, "model_version": "noshow-1.0.0",
 "disclaimer": "Educational demo trained on synthetic data. Not medical advice, not a diagnosis, and not a prediction about any real person or appointment."}

=== (2 lead_time_days 91, member) expected 400, got HTTP 400: as expected
{"error": {"code": "validation_error", "message": "Invalid input.",
  "fields": {"lead_time_days": ["Must be between 0 and 90."]},
  "request_id": "5c6b6fb4-c84c-4493-b5c1-e87032546e47"}}

=== (3 extra field role: 'admin', member) expected 400, got HTTP 400: as expected
{"error": {"code": "validation_error", "message": "Invalid input.",
  "fields": {"role": ["Unknown field."]},
  "request_id": "74843088-714f-437f-b336-d69a21860bb4"}}

=== (4 member, no X-CSRFToken header) expected 403, got HTTP 403: as expected
{"error": {"code": "permission_denied", "message": "CSRF failed: CSRF token missing.", "fields": {},
  "request_id": "640c0bb8-ae12-4dbb-9838-b6defc74a559"}}

=== (5 signed out (CSRF cookie + header, no sign-in)) expected 401, got HTTP 401: as expected
{"error": {"code": "not_authenticated", "message": "Authentication credentials were not provided.", "fields": {},
  "request_id": "01b1d79b-618e-4640-b4c7-e7c0612ab5ef"}}

=== (6 admin session (sessionid + X-CSRFToken)) expected 401, got HTTP 401: as expected
{"error": {"code": "not_authenticated", "message": "Authentication credentials were not provided.", "fields": {},
  "request_id": "31440307-8f8f-4854-bf8d-e56a4bd19fc5"}}

all six statuses as expected
```

(The script printed each body indented over several lines; it is shown here on fewer lines, with nothing changed.)
The same cases are also covered by automated tests in `backend/tests/test_ml_api.py`.

## Prompt refinement and the test that failed first (mentor review)

The PR #4 review asked for a link to one exact prompt refinement and to the test that failed before the fix. The
links point at `5f3a820`, a commit that is already pushed, so the line numbers cannot move.

* **The refinement: Week 2 prompt 12**
  ([docs/ai-workflow.md, lines 358–363](https://github.com/mominaasif-45/healthprofile/blob/5f3a8203568080512a8444a13f0b62bbc7b66686/docs/ai-workflow.md?plain=1#L358-L363)).
  Prompt 11 only asked for a plan for the contact deletion race. Prompt 12 tightened it in two ways:
  * it required tests E and F to be **shown failing on the current code with `-rs`** (so a skip could not pass for a
    success) before any fix;
  * it added the same gap in `update_contact` (a PATCH losing to a delete gave a 500), with its own test, G.
* **The tests that failed before the fix:**
  [`test_e_contact_made_primary_after_the_delete_read_it`](https://github.com/mominaasif-45/healthprofile/blob/5f3a8203568080512a8444a13f0b62bbc7b66686/backend/tests/test_concurrency.py#L351),
  [`test_f_…`](https://github.com/mominaasif-45/healthprofile/blob/5f3a8203568080512a8444a13f0b62bbc7b66686/backend/tests/test_concurrency.py#L377)
  and
  [`test_g_…`](https://github.com/mominaasif-45/healthprofile/blob/5f3a8203568080512a8444a13f0b62bbc7b66686/backend/tests/test_concurrency.py#L399)
  in `backend/tests/test_concurrency.py`.
* **Their saved failing output** on the old code `96e29a2`, which shows E left zero primaries, F's second delete
  "succeeded", and G hit a 500:
  [docs/evidence/week2-review.md, lines 159–165](https://github.com/mominaasif-45/healthprofile/blob/5f3a8203568080512a8444a13f0b62bbc7b66686/docs/evidence/week2-review.md?plain=1#L159-L165).
  With the fix (`dbe41db`, merged into this branch at `8835d56`) the same command gives `3 passed`.

## Test counts after the card wording change

Run on 8 November 2026 on the code of `a1e96ce` (no code changes in the working tree), `ML_SKIP_SLOW` not set:

```text
python -m pytest -rs: 429 passed in 205.86s (0:03:25)    (278 Week 1–2 + 151 Week 3; C1 added 2 report tests)
```

The frontend count is unchanged: 47 tests (23 for the card).

## PostgreSQL race tests in CI and on the Week 3 head (mentor review of PR #3)

The PR #3 review: `tests/test_concurrency.py` skips on any database that is not PostgreSQL, so a green SQLite run
cannot validate the race fix. The tests must run in a reproducible CI job that shows the database backend and the skip
summary, and fails if the intended race cases do not run.

**The CI job** ([`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), added in `4711574`):

* Runs on every push, on Ubuntu 24.04 with Python 3.13 and a `postgres:17` service.
* Uses throwaway CI-only settings written in the workflow, never `backend/.env`.
* Prints the tested commit, the database vendor and the server version. It stops if the vendor is not PostgreSQL.
* Runs `python -m pytest tests/test_concurrency.py -rs -vv`.
* Then [`.github/scripts/check_race_run.py`](../../.github/scripts/check_race_run.py) reads pytest's JUnit report and
  fails the job unless **exactly 9** race tests ran, with none skipped, failed or errored. pytest on its own would
  report a run where everything was skipped as a success.

**The guard was proved to fail** before it was committed (8 November 2026, the same script):

| Run | pytest | Guard |
|---|---|---|
| SQLite (`DATABASE_URL=sqlite://:memory:`) | `9 skipped`, exit 0 | `FAIL: 9 race test(s) were skipped` and `FAIL: expected 9 race tests to run, but 0 ran`, **exit 1** |
| PostgreSQL, test G left out (`-k "not test_g"`) | `8 passed, 1 deselected`, exit 0 | `FAIL: expected 9 race tests to run, but 8 ran`, **exit 1** |
| PostgreSQL, all tests | `9 passed`, exit 0 | `OK: every race test ran on PostgreSQL and passed`, **exit 0** |

**First CI run, on `4711574`: green.**
[Actions run 42509900392, job "Race tests (PostgreSQL 17)"](https://github.com/mominaasif-45/healthprofile/actions/runs/42509900392/job/128820476023).

**Local run on the Week 3 head.** Tested commit `471157467bfba53f8cb471fefcf1673ddcb53cec` (the pushed head at the
time), clean working tree, 8 November 2026. Run from `backend/` with the venv active:

```text
> git status --short
(nothing: clean working tree, before and after the run)

> git log -1 --format="Tested commit: %H %s"
Tested commit: 471157467bfba53f8cb471fefcf1673ddcb53cec ci: run PostgreSQL race tests in GitHub Actions and fail if any is skipped

> python -c "...print the database vendor and server version..."
vendor: postgresql
server: PostgreSQL 17.11 on x86_64-windows, compiled by msvc-19.44.35229, 64-bit

> python -m pytest tests/test_concurrency.py -rs -vv
platform win32 -- Python 3.13.16, pytest-9.1.1, pluggy-1.7.0
django: version: 6.1.2, settings: config.settings (from ini)
collecting ... collected 9 items

tests/test_concurrency.py::test_a_member_passed_the_early_check_then_admin_deactivated[patch demographics] PASSED [ 11%]
tests/test_concurrency.py::test_a_member_passed_the_early_check_then_admin_deactivated[create contact] PASSED [ 22%]
tests/test_concurrency.py::test_a_member_passed_the_early_check_then_admin_deactivated[delete profile] PASSED [ 33%]
tests/test_concurrency.py::test_b_member_waits_for_the_admins_lock_then_sees_the_deactivation PASSED [ 44%]
tests/test_concurrency.py::test_c_admin_waits_for_the_members_lock_and_the_member_write_counts PASSED [ 55%]
tests/test_concurrency.py::test_d_two_admin_deactivations_record_exactly_one_status_change PASSED [ 66%]
tests/test_concurrency.py::test_e_contact_made_primary_after_the_delete_read_it PASSED [ 77%]
tests/test_concurrency.py::test_f_contact_deleted_by_another_request_after_the_delete_read_it PASSED [ 88%]
tests/test_concurrency.py::test_g_contact_deleted_by_another_request_after_the_patch_read_it PASSED [100%]

============================= 9 passed in 27.25s ==============================

> python ..\.github\scripts\check_race_run.py race-results.xml 9     (pytest also given --junitxml)
race tests: expected 9, ran 9, skipped 0, failed 0, errors 0
OK: every race test ran on PostgreSQL and passed
```

**Skip summary:** `-rs` asks pytest to list every skipped test with its reason. It printed none, and the guard counted
0 skipped: all 9 race cases ran on PostgreSQL.

The commit that adds this section changes only documentation. CI runs again on it after the push, so the final head
is also checked on PostgreSQL.
