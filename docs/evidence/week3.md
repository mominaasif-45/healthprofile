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
