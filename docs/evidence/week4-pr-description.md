# Week 4: comparative ML workbench, exploratory clusters, local LLM endpoint and FAQ assistant (RAG)

**Stacked PR.** Base: `feature/week3-ml-pipeline` (PR #4) · Head: `feature/week4-ml-llm-rag`.
Please review PR #4 first; this PR shows only the Week 4 changes on top of it. Merge order: PR #4, then this one
(GitHub retargets it automatically when its base is merged).

> Educational demo on synthetic data. Not medical advice and not a diagnosis. The policies are fictional, the language
> model runs on the local computer, and no profile data is sent to it. The shipped prediction model is still
> `noshow-1.0.0`.

## Summary

- **Supervised workbench**: baseline, logistic regression, tuned random forest and gradient boosting compared on the
  Week 3 synthetic data with every metric the brief asks for, cross-validation, permutation importance and error
  inspection. Every choice is made on validation only, because the test pile was already used in Week 3.
- **Exploratory clusters**: K-Means and Ward on five engagement features, elbow, silhouette and a PCA view. The
  structure is weak (silhouette 0.26) and the report says so.
- **LLM endpoint** `POST /api/llm/v1/faq/ask/`: a `fake` / `ollama` provider adapter (`fake` is the default and is
  always used in tests and CI), strict JSON replies, a personal-details refusal, a throttle, timeouts and safe errors.
- **RAG over fictional policies**: admin-only upload, chunking, `nomic-embed-text` embeddings in PostgreSQL, cosine
  search, citations verified against the passages that were sent, and `insufficient_information` instead of a guess.
- **Evaluation**: 12 fixed cases, prompt A against a one-line variant B (A 11 / 12, B 9 / 12), and a re-check of the
  0.62 similarity threshold.
- **`/ml` dashboard**: Supervised, Clusters and FAQ assistant tabs, with versions, metrics and disclaimers.

## What changed, per phase

| Commit | Phase | Main files |
|---|---|---|
| `af7ecbf` | 1. Supervised workbench | `backend/ml/workbench.py`, `ml/models.py` (random forest + tuning), `ml/views.py`, `ml/urls.py`, `ml/reports/workbench.json`, `docs/ml/workbench-report.md`, `tests/test_ml_workbench.py` (29) |
| `0667e71` | 2. Exploratory clusters | `backend/ml/clusters.py`, shared report view in `ml/views.py`, `ml/reports/clusters.json`, `docs/ml/clusters-report.md`, `tests/test_ml_clusters.py` (27) |
| `ccdc88c` | 3. LLM endpoint | new `backend/llm/` app (providers, privacy, prompts, schema, service, views), settings and URL, `tests/test_llm_faq.py` |
| `ff9f811` | 4. RAG | `llm/models.py` + migration `0001`, `extract.py`, `chunking.py`, `embeddings.py`, `ingest.py`, `retrieval.py`, upload view, `llm/policies/*.md`, `seed_policies`, `tests/test_llm_rag.py` (73); `test_llm_faq.py` now 78 |
| `f07053e` | 5. Evaluation | `llm/eval/` (`prompts.json`, `variants.py`, `scoring.py`, `run.py`, `results.json`), `docs/llm/evaluation.md`, `tests/test_llm_eval.py` (22) |
| `d8dd7f0` | Fix | `frontend/next.config.ts`: Next.js proxy timeout 30 s → 120 s |
| `55d2832` | 6. Dashboard | `frontend/app/ml/page.tsx`, `components/ml/*`, `lib/ml.ts`, `tests/ml-page.test.tsx`, `tests/ml-lib.test.ts` (33) |
| docs commit | 7. Docs | README "What is new in Week 4", `docs/evidence/week4.md`, `docs/screenshots/week4/`, this description, `docs/ai-workflow.md` |

## How to run

```bash
cd backend
pip install -r requirements.txt     # unchanged in Week 4: no new packages
python manage.py migrate            # adds llm 0001
python manage.py seed_policies      # loads the 5 fictional policies with the current embedder
python manage.py runserver
cd ../frontend && npm run dev       # then sign in as a member and open http://localhost:3000/ml
```

The default provider is `fake` (no network, instant). For the real local model: install Ollama, run
`ollama pull llama3.2:3b` and `ollama pull nomic-embed-text`, add `LLM_PROVIDER=ollama` to your own `backend/.env`,
run `python manage.py seed_policies` again, and restart both servers. Real answers take about 30 to 76 s on a laptop
CPU. Details: README, "Run it (Week 4)".

## Test evidence

Tested commit: **`55d28321f3870c098d15f8cdaa479197d3a2fe36` (`55d2832`)**. Full output and the phase-by-phase evidence (tests shown failing first, three
break-it checks per phase, real timings and memory): [`docs/evidence/week4.md`](docs/evidence/week4.md).

| Check | Result on `55d2832` |
|---|---|
| Backend `python -m pytest` | **658 passed, 0 skipped** (429 Weeks 1-3 + 229 Week 4), 7 min 12 s |
| Same suite with the provider pointed at a closed Ollama port | 658 passed: no test needs Ollama |
| PostgreSQL race tests + guard | 9 passed; "ran 9, skipped 0" |
| `python -m ml.train --check` | `noshow-1.0.0` rebuilt byte for byte, SHA-256 `d69f7723…8218` |
| Frozen Week 1-3 files vs `feature/week3-ml-pipeline` | no diff (only the two one-line edits below) |
| `makemigrations --check` / `spectacular --validate --fail-on-warn` | No changes / no warnings |
| `npm run lint` / `npm test` / `npm run build` | clean / **80 passed** (47 + 33) / 12 of 12 static pages, `/ml` included |
| Evaluation cases file | SHA-256 `71147923…`, unchanged since it was saved before the first run |
| Real browser run (local model) | answered with a verified citation in 74 s (cold), insufficient information, email refused, `.pdf` refused; screenshots in `docs/screenshots/week4/` |

CI on push runs the 9 PostgreSQL race tests with the "ran 9, skipped 0" guard (unchanged from PR #4). The other
backend tests and the frontend tests are not run in CI today; see "Notes for the reviewer".

## Security notes

- **No patient data to the model.** The LLM code never reads profile data (tested). Questions with an email address,
  7 or more digits or the member's own name are refused with 400 before retrieval or any model call; uploads with
  personal details are refused too.
- **Local only.** The provider only sends to `localhost` / `127.0.0.1` / `::1` (checked before sending) and ignores
  proxy settings. There is no API key.
- **Retrieved documents are untrusted.** They go in the user message inside `<document id>` tags, never in the system
  prompt; fake tags are defused. Every citation must come from a passage that was sent and appear in it; boilerplate
  quotes are removed; an answer repeating the system prompt is dropped.
- **Upload is admin-only** (session + CSRF, like every admin route): `.txt` / `.md` only, at most 200 KB, UTF-8, no
  NUL bytes, no personal details, stored in one transaction.
- **Limits and errors.** Throttles: ask 10 / min per member, upload 20 / min, reports 60 / min. Timeouts: chat 100 s,
  embeddings 60 s. Errors use the usual `{"error": {"code", "message", "fields"}}` shape with fixed messages: no
  stack traces, no raw model text, nothing from the question or file. Questions and answers are not stored or logged.
- **Project rules kept.** Every new view declares authentication and permission classes; no member route takes an id;
  no `role` / `status` / `is_staff` / `is_superuser` from a body; no new dependencies; one new migration
  (`llm/0001`), no applied migration edited.

## Limitations

- `llama3.2:3b` is small and runs on the CPU: answers take about 30 to 76 s, and it sometimes quotes the wrong
  sentence (evaluation case A3).
- The cluster structure is weak (silhouette 0.26 at k = 2; Ward agreement 0.594); the clusters are exploratory only.
- The evaluation has 12 cases and one run, with 4 failures in 24 runs; it does not show that one prompt is better.
- The citation check is strict on purpose and refused one correct answer whose quote dropped two words.
- The 0.62 similarity threshold is fixed, with a narrow gap (covered probes from 0.633, uncovered up to 0.607).
- Synthetic data and fictional policies only; not medical advice. Cost is reported as 0.00 because the model is local
  (hardware and electricity not counted).
- The workbench reuses the Week 3 test pile, so it is reported but never used to choose. No upload audit event (it
  would need a migration in the frozen `audit` app).

## Files outside Week 4 that changed

| File | Change |
|---|---|
| `frontend/next.config.ts` | +3 lines: `experimental: { proxyTimeout: 120_000 }` and a two-line comment (commit `d8dd7f0`) |
| `frontend/app/profile/page.tsx` | +1 line: the "ML dashboard" link in the profile side menu (commit `55d2832`) |

Shared configuration that Week 4 extends (approved in the plan): `backend/config/settings.py` (LLM settings, throttle
rates, `llm` and `django.contrib.postgres` apps), `backend/config/urls.py` (one `include`), `backend/.env.example`
(commented LLM settings, default `fake`), `backend/ml/models.py`, `backend/ml/views.py`, `backend/ml/urls.py` (Week 3
code unchanged), `README.md` and `docs/ai-workflow.md`. Every other Week 1 to 3 file has no diff against the base.

## Notes for the reviewer

- **CI coverage.** `.github/workflows/ci.yml` runs only the 9 PostgreSQL race tests on push. They are expected to stay green (no new requirements; the new `llm` migration only needs `django.contrib.postgres`, which ships with Django). The Week 4 backend tests and all frontend tests are **not** run in CI, just like the Week 1-3 non-race tests before them. They need no Ollama (shown above), so adding a backend job (full `pytest` on the same PostgreSQL service) and a frontend job (`npm ci`, `npm test`, `npm run lint`, `npm run build`) would be a small follow-up if the reviewer wants it.
- Screenshots of the real page with the real model: `docs/screenshots/week4/` (listed in the README).
