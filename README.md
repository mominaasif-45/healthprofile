# HealthProfile

## Problem statement

People need a private place to keep a wellness profile, and clinic staff need a secure way to search and
review those profiles. The two groups must never be mixed up: members and admins sign in through **two
separate auth systems**, so a member can never reach an admin feature, even by tampering with the browser.
Every edit and every admin action is recorded in an **audit trail** that stores field names, never values.
All data in this project is synthetic.

> **Demo environment.** Every profile is synthetic. No real patient data. Wellness goals only,
> never diagnoses or medical advice.

## What is new in Week 4

Week 4 ("Comparative ML Workbench, Clustering, LLM Endpoint and FAQ Assistant") adds four things on top of Week 3, and
one page that shows them:

1. a **supervised workbench** that compares four models on the Week 3 synthetic appointments;
2. **exploratory clusters** of booking behaviour;
3. an **LLM endpoint** that runs a small local model (Ollama, `llama3.2:3b`) behind a provider adapter;
4. an **educational FAQ assistant** that answers only from approved fictional policies, with verified citations (RAG);
5. the **`/ml` dashboard** with three tabs (Supervised, Clusters, FAQ assistant), and a **12-case evaluation** of two
   system prompts.

> **Educational demo on synthetic data.** Not medical advice and not a diagnosis. The policies are fictional, the
> model runs on this computer, and no profile data is ever sent to it. The shipped prediction model is still
> `noshow-1.0.0` from Week 3.

Real command output and every check: [docs/evidence/week4.md](docs/evidence/week4.md). Reports:
[workbench](docs/ml/workbench-report.md), [clusters](docs/ml/clusters-report.md),
[LLM evaluation](docs/llm/evaluation.md).

### Feature checklist (Week 4)

- [x] **Supervised workbench**: baseline, logistic regression, random forest (tuned with `RandomizedSearchCV`, 10 tries)
  and histogram gradient boosting. Confusion matrix, precision, recall, F1, ROC-AUC, PR-AUC, train vs validation,
  5-fold stratified cross-validation, permutation importance, false positive and false negative inspection, all in one
  reproducible scikit-learn pipeline per model ([`ml/workbench.py`](backend/ml/workbench.py),
  [report](docs/ml/workbench-report.md))
- [x] **Every choice made on the validation pile only**; the test pile (already used once in Week 3) is reported
  afterwards and never used to choose
- [x] **Exploratory clusters**: K-Means (k = 2 to 8, elbow and silhouette) and Agglomerative (Ward) on five engagement
  features only (no age band, distance band or no-show label), fitted on training rows only, with a 2D PCA view
  ([`ml/clusters.py`](backend/ml/clusters.py), [report](docs/ml/clusters-report.md))
- [x] **LLM endpoint** `POST /api/llm/v1/faq/ask/`: system prompt, task prompt, fixed context window (2,048 tokens),
  token limit (300), temperature (0.2), strict JSON reply schema, throttle, timeout, safe errors, token counts and cost
  ([`backend/llm/`](backend/llm/))
- [x] **FAQ assistant over fictional policies**: admin-only upload (`.txt` / `.md`, 200 KB, UTF-8), text extraction,
  chunking, `nomic-embed-text` embeddings stored in PostgreSQL, cosine search with numpy, cited passages, and an
  explicit `insufficient_information` answer instead of a guess
- [x] **12-case evaluation** (answerable, ambiguous, out of scope, prompt injection) comparing prompt A with a one-line
  variant B, plus a re-check of the similarity threshold ([`llm/eval/`](backend/llm/eval/),
  [report](docs/llm/evaluation.md))
- [x] **`/ml` dashboard**: three keyboard-accessible tabs showing model versions, metrics and disclaimers; charts in
  plain SVG with text labels; an upload panel for admins only
- [x] **Weeks 1 to 3 still work**: the frozen Week 1 to 3 files have no diff, `noshow-1.0.0` is rebuilt byte for byte,
  the 9 PostgreSQL race tests run with none skipped
- [x] **Tests**: 229 new backend tests (658 in total) and 33 new frontend tests (80 in total)

### How it fits together

The FAQ assistant answers one question like this ([`llm/service.py`](backend/llm/service.py)):

```
question  POST /api/llm/v1/faq/ask/  (member JWT cookie + CSRF, 10 per minute)
   │
   ▼  1. strict input        only {"question": ...}, 3 to 500 characters; any other field is a 400
   ▼  2. privacy check       an email address, 7 or more digits (phone, ID, a date in digits) or the member's own
   │                         name -> 400, and nothing is sent anywhere
   ▼  3. retrieval           embed the question (nomic-embed-text) -> cosine similarity against the stored chunks
   │                         -> top 3 chunks with similarity >= 0.62. None -> insufficient_information (no model call)
   ▼  4. untrusted prompt    fixed system prompt with the rules; each chunk goes in the USER message inside
   │                         <document id="..."> tags marked as untrusted data; fake tags inside a chunk are defused
   ▼  5. model               llama3.2:3b on local Ollama (127.0.0.1 only), temperature 0.2, at most 300 tokens,
   │                         2,048-token context, 100 s timeout (504), unreachable (503)
   ▼  6. schema check        the reply must be exactly {status, answer, citations[]}; anything else -> 502, raw text
   │                         never shown
   ▼  7. citation check      each quote must come from a chunk that was sent, appear in that chunk (ignoring case and
   │                         spacing), be at least 12 characters, and not be boilerplate found in two or more
   │                         documents; an answer that repeats the system prompt is dropped
   ▼  8. answer              answered (with verified citations) | insufficient_information | out_of_scope, the last
                             two as fixed sentences; plus retrieval settings, tokens, cost 0.00, time, disclaimer
```

The two report endpoints are simpler: `GET /api/ml/v1/workbench/` and `GET /api/ml/v1/clusters/` return the committed
JSON reports (`backend/ml/reports/workbench.json`, `clusters.json`) that `python -m ml.workbench` and
`python -m ml.clusters` write. They take no input and change nothing.

| New in `backend/` | What it does |
|---|---|
| `ml/workbench.py`, `ml/models.py` (random forest + tuning added) | The supervised comparison and its report |
| `ml/clusters.py` | Clusters, elbow, silhouette, PCA and the cluster report |
| `ml/views.py` | One shared read-only view for both reports (members only, 60 per minute) |
| `llm/providers.py` | The provider adapter: `fake` (default, no network) or `ollama` (urllib, local address only, proxies ignored) |
| `llm/privacy.py`, `llm/prompts.py`, `llm/schema.py`, `llm/service.py` | The privacy check, the prompts, the reply schema, and the steps above |
| `llm/extract.py`, `llm/chunking.py`, `llm/embeddings.py`, `llm/ingest.py`, `llm/retrieval.py`, `llm/models.py` | Upload checks, chunks of 600 characters with 100 overlap, embeddings, storage (PostgreSQL `float8[]`), search |
| `llm/policies/*.md`, `llm/management/commands/seed_policies.py` | Five short fictional policies and the command that loads them |
| `llm/eval/` | The 12 cases, prompt variant B, the scorer, the runner and its saved results |

### Run it (Week 4)

Start from "Run it locally" below; Week 4 adds no new packages. Then, in `backend/` with the venv active:

```bash
python manage.py migrate            # adds llm 0001 (policy documents and chunks)
python manage.py seed_policies      # loads backend/llm/policies/*.md with the CURRENT embedder
python manage.py runserver
```

and in `frontend/`: `npm run dev`, sign in as a member, and open **ML dashboard** in the side menu
(http://localhost:3000/ml).

**Fake or real model.** Out of the box `LLM_PROVIDER` is `fake`: no network, instant answers that say they come from
the test assistant. Tests and CI always use it. To use the real local model:

1. Install Ollama and pull the two models: `ollama pull llama3.2:3b` and `ollama pull nomic-embed-text`
   (about 1.9 GB and 0.3 GB on disk). Check with `ollama list`.
2. In **your own** `backend/.env`, add one line: `LLM_PROVIDER=ollama`. The embedder follows it (`LLM_EMBEDDER`
   defaults to the provider). The other settings have working defaults: `LLM_BASE_URL=http://127.0.0.1:11434` (must be
   this computer; the code refuses anything else), `LLM_MODEL=llama3.2:3b`, `LLM_EMBED_MODEL=nomic-embed-text`,
   `LLM_TIMEOUT_SECONDS=100`.
3. Run `python manage.py seed_policies` again. Search only uses chunks made by the current embedder, so this step is
   needed after every embedder change. It prints `embedder: ollama:nomic-embed-text` and the counts.
4. Restart `runserver` (it reads `.env` only at start) and `npm run dev`.
5. Ask a question on the FAQ tab. Under the answer the page shows `Model: llama3.2:3b (ollama)`; with the fake
   provider it shows `fake`.

Rebuild the two reports (both are deterministic and compared against the committed files by tests):

```bash
python -m ml.workbench              # about 2.5 minutes, one CPU core
python -m ml.clusters               # about 20 seconds
python -m llm.eval.run              # the 12-case evaluation against the REAL model (about 6.5 minutes)
```

Tests:

```bash
cd backend
python -m pytest                    # 658 passed (429 Weeks 1-3 + 229 Week 4), about 4 to 7 minutes on this laptop (final run: 7 min 12 s; other Week 4 runs 3 min 23 s to 6 min 26 s)
cd ../frontend
npm test                            # 80 passed (47 Weeks 1-3 + 33 Week 4)
```

| New test file | What it proves |
|---|---|
| `test_ml_workbench.py` (29) | Random forest is one pipeline on the Week 3 preprocessor; fill-in values come from training rows only; folds are stratified and inside the training pile; the tuning tried 10 settings and reports the real best; confusion matrices match scikit-learn; the choice uses validation only; the committed report matches a fresh run; Week 3 files untouched; the endpoint's 401 / 405 / 200 |
| `test_ml_clusters.py` (27) | Exactly the 5 engagement features; scaler, PCA and K-Means fitted on the 4,200 training rows; the k rule; Ward and the agreement score; PCA points; no "risk group" or similar words; the committed report matches a fresh run; the endpoint |
| `test_llm_faq.py` (78) | Sign-in, CSRF, the throttle; unknown fields refused; personal details refused and never sent; profile data never in the prompt; the reply schema (every bad reply gives 502); timeout 504, unreachable 503; local address only; tokens and cost; nothing logged |
| `test_llm_rag.py` (73) | Upload: admins only, type, size, UTF-8, binary, personal details, duplicates, embedder down; chunking; retrieval and the threshold; documents in the user message, never the system prompt; injection inside a document; every citation rule; insufficient information; `seed_policies` |
| `test_llm_eval.py` (22) | The 12 cases are new and saved first; prompt B changes exactly one line; the scorer marks a leak, an obeyed injection, a missing citation and a wrong status; timeouts are recorded |
| `frontend/tests/ml-page.test.tsx`, `ml-lib.test.ts` (33) | Tabs and keyboard; versions, metrics and disclaimers from mocked responses; the thinking state and no double submit; citations; every error code maps to a fixed safe message; the upload is hidden from non-admins; banned words never appear |

### API examples (real output)

Sign in once with curl (cookies go to a jar; no token is ever in a body). Use your own fictional demo account:

```bash
curl -s -c jar.txt http://127.0.0.1:8000/api/csrf/ > /dev/null
CSRF=$(awk '$6=="csrftoken" {print $7}' jar.txt)
curl -s -b jar.txt -c jar.txt -H "X-CSRFToken: $CSRF" -H "Content-Type: application/json" \
     -d '{"email": "momina.asif@example.com", "password": "<your password>"}' \
     http://127.0.0.1:8000/api/auth/user/login/
CSRF=$(awk '$6=="csrftoken" {print $7}' jar.txt)       # Django rotates the token at login
```

The same requests can be tried in Swagger at http://127.0.0.1:8000/api/docs/ (groups *ml demo (educational)* and
*llm faq (educational)*).

**Workbench** `GET /api/ml/v1/workbench/` (member, 60 per minute) → **200**, the committed report (abridged):

```bash
curl -s -b jar.txt http://127.0.0.1:8000/api/ml/v1/workbench/
```

```json
{"version": "workbench-1.0.0",
 "disclaimer": "Educational comparison on synthetic data. Not medical advice, not a diagnosis, and not a prediction about any real person or appointment. This report ships no model: the API still uses noshow-1.0.0.",
 "test_pile_note": "The test pile was already used in Week 3 to report the baseline, logistic regression and gradient boosting, so it is no longer completely unseen. …",
 "settings": {"split_seed": 42, "model_seed": 42, "cv_folds": 5, "rf_search_tries": 10, "permutation_repeats": 10,
              "overfit_gap": 0.05, "leakage_margin": 0.03, "scikit_learn": "1.9.1", "shipped_model": "noshow-1.0.0"},
 "pile_sizes": {"train": {"rows": 4200, "no_shows": 874}, "validation": {"rows": 900, "no_shows": 187}, "test": {"rows": 900, "no_shows": 187}},
 "models": {"logistic_regression": {
     "cv": {"rows": 4200, "pr_auc": {"mean": 0.3468, "sd": 0.0437, "folds": [0.3221, 0.2833, 0.4137, 0.3675, 0.3472]}, "…": "…"},
     "validation": {"roc_auc": 0.6269, "pr_auc": 0.308, "threshold": 0.22, "precision": 0.3086, "recall": 0.5348,
                    "f1": 0.3914, "tp": 100, "fp": 224, "fn": 87, "tn": 489, "…": "…"},
     "gap": {"pr_auc": 0.0583, "overfit": true}, "…": "…"},
   "baseline": {"…": "…"}, "random_forest": {"…": "…"}, "gradient_boosting": {"…": "…"}},
 "best_on_validation": "random_forest",
 "rf_search": ["… 10 settings …"], "importance": {"…": "…"}, "errors": {"…": "…"}, "test": {"…": "…"}}
```

**Clusters** `GET /api/ml/v1/clusters/` (member, 60 per minute) → **200** (abridged; `pca.points` holds 500 points):

```json
{"version": "clusters-1.0.0",
 "disclaimer": "Exploratory analysis of synthetic data. Not medical advice and not a diagnosis. The clusters are not kinds of people and are not used for any decision or prediction.",
 "features": ["lead_time_days", "prior_visits", "prior_no_shows", "reminder_sent", "booking_channel"],
 "elbow": [{"k": 2, "inertia": 13408.2293, "silhouette": 0.2598}, {"k": 3, "inertia": 11094.3517, "silhouette": 0.2561}, "… k = 4 to 8 …"],
 "chosen_k": 2,
 "structure_note": "The chosen k is 2 with an average silhouette of 0.26, which reads as weak structure. …",
 "kmeans": {"silhouette": 0.2598, "sizes": [3055, 1145]},
 "agglomerative": {"k": 2, "linkage": "ward", "silhouette": 0.2191, "sizes": [2742, 1458], "adjusted_rand_vs_kmeans": 0.5938},
 "validation": {"rows": 900, "sizes": [688, 212], "silhouette": 0.254},
 "pca": {"explained_variance": [0.3298, 0.2467], "points": [[4.166, -0.502, 2], "…"]},
 "summary": [{"cluster": 1, "rows": 3055, "share": 0.7274,
              "description": "Books about as far ahead as average (12 days); less often has an earlier missed visit (9% vs 31%); mixed booking channels.", "…": "…"},
             {"cluster": 2, "…": "…"}]}
```

**Ask** `POST /api/llm/v1/faq/ask/` (member + CSRF, 10 per minute):

```bash
curl -s -b jar.txt -H "X-CSRFToken: $CSRF" -H "Content-Type: application/json" \
     -d '{"question": "How many emergency contacts can I add?"}' http://127.0.0.1:8000/api/llm/v1/faq/ask/
```

**200**, a real call with the local model on 10 November 2026 (cold start: the model had to load, so 74 s):

```json
{
 "status": "answered",
 "answer": "A member can add up to three emergency contacts to a profile.",
 "citations": [
  {
   "chunk_id": "3",
   "document_id": 2,
   "document_title": "Emergency contacts",
   "quote": "A member can add up to three emergency contacts to a profile."
  }
 ],
 "retrieval": {
  "top_k": 3,
  "min_similarity": 0.62,
  "chunk_size": 600,
  "chunk_overlap": 100,
  "embedding_model": "ollama:nomic-embed-text",
  "best_similarity": 0.7841,
  "chunks_sent": 3,
  "unverified_citations_removed": 0
 },
 "provider": "ollama",
 "model": "llama3.2:3b",
 "prompt_version": "faq-system-2",
 "usage": {
  "prompt_tokens": 706,
  "completion_tokens": 54,
  "total_tokens": 760,
  "source": "provider"
 },
 "cost": {
  "amount": "0.00",
  "currency": "USD",
  "note": "Local model on this computer: no per-token charge. Hardware and electricity are not counted."
 },
 "latency_ms": 73753,
 "disclaimer": "Educational demo on synthetic data. Answers come only from fictional HealthProfile demo policies: not medical advice, not a diagnosis, and not a decision about any real person."
}
```

**200** for `"What is the capital of France?"`: no passage reached 0.62 (best 0.4742), so the model was **not called**:

```json
{
 "status": "insufficient_information",
 "answer": "I could not find this in the approved HealthProfile demo policies, so I will not guess. Try rephrasing, or ask about a topic the policies cover.",
 "citations": [],
 "retrieval": {
  "top_k": 3,
  "min_similarity": 0.62,
  "chunk_size": 600,
  "chunk_overlap": 100,
  "embedding_model": "ollama:nomic-embed-text",
  "best_similarity": 0.4742,
  "chunks_sent": 0,
  "unverified_citations_removed": 0
 },
 "provider": "none",
 "model": "none",
 "prompt_version": "faq-system-2",
 "usage": {
  "prompt_tokens": 0,
  "completion_tokens": 0,
  "total_tokens": 0,
  "source": "none"
 },
 "cost": "… same as above …",
 "latency_ms": 228,
 "disclaimer": "… same as above …"
}
```

**400** for `"Please email me at someone@example.com about my contacts"`: refused before anything was sent, and the
email is not repeated:

```json
{"error": {"code": "validation_error", "message": "Invalid input.", "fields": {"question": ["Please remove personal details (names, email addresses, phone or ID numbers, dates of birth) before asking. They are never sent to the assistant."]}, "request_id": "28282670-6182-4507-8855-34da1cccc3e9"}}
```

**Policy upload** `POST /api/llm/v1/policies/` (**admins only**: admin session + CSRF, 20 per minute). Sign in at
`/api/admin/login/` in the same way, then send one file in the `file` field:

```bash
curl -s -b admin-jar.txt -H "X-CSRFToken: $CSRF" -F "file=@my-fictional-policy.md" http://127.0.0.1:8000/api/llm/v1/policies/
```

**201** (a throwaway fictional file, uploaded once to record this response and then deleted):

```json
{"id": 11, "title": "Readme example", "filename": "week4-readme-example.md", "sha256": "6de2424e859cc7be3efe6249bcf6ebc44b766d5575e3909d5870db614f3bb545", "size_bytes": 188, "chunks": 1, "embedding_model": "ollama:nomic-embed-text", "chunk_size": 600, "chunk_overlap": 100}
```

**400** for a `.pdf`:

```json
{"error": {"code": "validation_error", "message": "Invalid input.", "fields": {"file": ["Only .txt and .md files can be uploaded."]}, "request_id": "ed650f35-0f1c-45e3-af33-9ef8cd344867"}}
```

| Endpoint | Status codes |
|---|---|
| workbench, clusters | 200; 401 not signed in as a member (an admin session too); 405 for anything but GET; 429; 503 `report_unavailable` if the committed file cannot be read |
| ask | 200 (`answered`, `insufficient_information` or `out_of_scope`); 400 invalid input, unknown field or personal details; 401; 403 missing CSRF; 429 more than 10 a minute; 502 `llm_bad_reply`; 503 `llm_unavailable`; 504 `llm_timeout` |
| policy upload | 201; 400 wrong type, too big, not UTF-8, binary, empty, personal details or unknown field; 403 not an admin or missing CSRF; 409 `duplicate_document`; 429; 503 / 504 embedder down or too slow (nothing stored) |

### Safety design (Week 4)

| Rule | How it is enforced |
|---|---|
| **No patient data reaches the model** | Profile data is never read by the LLM code (a test checks the prompt). Questions with an email address, 7 or more digits or the member's own name are refused with 400 **before** retrieval or any model call; uploads with personal details are refused the same way. Refused, not stripped: cutting part of a question changes what was asked, and what is left can still identify someone |
| **Local model only** | The provider sends requests only to `localhost`, `127.0.0.1` or `::1` (checked before anything is sent) and ignores proxy settings, so a question cannot leave the computer. No API key exists, so none can leak |
| **Retrieved documents are untrusted** | Chunks go in the user message inside `<document id>` tags, never in the system prompt; the prompt says they are reference text, not instructions; a fake `</document>` inside a chunk is defused. Tested with an injected policy, and once for real (the model ignored it) |
| **Answers must be backed by the documents** | Strict reply schema; every citation verified against what was sent; boilerplate quotes removed; no verified citation means `insufficient_information`, never a guess; an answer that repeats the system prompt is dropped |
| **Upload is admin-only and validated** | Admin session + CSRF (the same rules as every admin route; there is still no public admin signup). `.txt` / `.md` as the last extension only, at most 200 KB (refused before reading), valid UTF-8, no NUL bytes, not empty, no personal details; the browser's content type is ignored; document and chunks saved in one transaction |
| **Limits** | Throttles: ask 10 per minute per member, upload 20, reports 60. Timeouts: chat 100 s, embeddings 60 s. Reply at most 300 tokens, context 2,048 tokens |
| **Safe errors** | The usual `{"error": {"code", "message", "fields"}}` shape with fixed messages: no stack traces, no raw model text, no question or file content. Logs hold the error type only; questions and answers are never stored or logged |
| **The members' rules still hold** | Every new view declares its authentication and permission classes; no member route takes an id; no `role`, `status`, `is_staff` or `is_superuser` is read from a body |

### Limitations (Week 4)

- **A small local model.** `llama3.2:3b` runs on the CPU. It sometimes quotes the wrong sentence or picks the wrong
  status even when the right passage was sent (case A3 in the evaluation).
- **Slow answers: about 30 to 76 seconds** for a real question on this laptop (the first call also loads the model;
  measured cold 36 to 76 s, warm 16 to 27 s). The page shows a "Thinking… N s" timer, the backend waits up to 100 s,
  and the Next.js proxy was raised to 120 s for this (see the evidence file). With both models loaded Ollama uses about
  2.6 GB of memory (3.3 GB peak during the evaluation), and by Ollama's default the models stay loaded for 5 minutes
  after the last question.
- **Weak cluster structure.** The best silhouette is **0.26** at k = 2 (k = 3 is almost tied at 0.256), K-Means and
  Ward agree only partly (adjusted Rand 0.594), and the 2D view keeps 58% of the spread. The clusters are exploratory
  and say nothing about who anyone is.
- **A small evaluation.** **12 cases, one run.** Prompt A got 11 of 12 right and prompt B 9 of 12, so there were **4
  failures** in 24 runs (1 for A, 3 for B), all on answerable questions. That is not enough to say one prompt is
  better, and results can change between runs.
- **A strict citation check.** A quote must match the passage (ignoring case, spacing and Markdown marks). One correct
  answer was refused because the model dropped two words from its quote. This is on purpose: a looser check would let
  invented quotes through.
- **A fixed similarity threshold of 0.62 with a narrow gap.** Covered probe questions scored 0.633 to 0.770 and
  uncovered ones 0.423 to 0.607, from only 14 probes. A new question can land on the wrong side. Most out-of-scope
  questions never reach the model because of it, so `out_of_scope` is rare.
- **A verified quote does not prove the whole answer**; the answer can still add words beyond the quote.
- **Synthetic data and fictional policies only. Not medical advice**, not a diagnosis, not a decision about any real
  person.
- **Cost is 0.00 because the model is local**: no per-token charge. Hardware and electricity are not counted, and
  embedding calls are not included in the token counts.
- **The workbench reused the test pile** from Week 3, so every choice uses validation only (see "Limitations" at the
  end). The workbench ships no model.
- **No upload audit event and no document list.** An audit action would need a migration in the frozen `audit` app;
  the document stores `uploaded_by` instead. With the fake embedder, almost every question gets
  `insufficient_information`, because the 0.62 threshold was set for `nomic-embed-text`.

## What is new in Week 3

Week 3 ("Machine Learning Pipeline and Prediction API") adds an **educational demo**: a model that estimates the
chance that a **fictional** appointment is missed (a "no-show"). It is trained only on synthetic data made by a seeded
script, is served by a versioned API endpoint, and is shown in a clearly labelled card on the member dashboard.

> **Educational demo on synthetic data.** Not medical advice, not a diagnosis, and not a prediction about any real
> person or appointment. The model never reads profile data.

Details live in three generated documents: the [data card](docs/ml/data-card.md) (where the data comes from and its
limits), the [analysis](docs/ml/eda.md) (training data only) and the [model report](docs/ml/model-report.md)
(every metric, group result and error). Real command output: [docs/evidence/week3.md](docs/evidence/week3.md).

### Feature checklist (Week 3)

- [x] **Synthetic data with provenance, licence, schema and limits**: 6,000 appointments from a seeded generator with an
  adjustable noise level ([`ml/data/generate.py`](backend/ml/data/generate.py), [data card](docs/ml/data-card.md))
- [x] **Exploratory analysis, missing values, train / validation / test split, no leakage**: split first (70/15/15,
  stratified), fill-in values learned from training rows only, analysis on training rows only
  ([`ml/features.py`](backend/ml/features.py), [`ml/analysis.py`](backend/ml/analysis.py))
- [x] **Baseline and improved models compared with imbalance-aware metrics, plus error analysis**: baseline, logistic
  regression and gradient boosting; PR-AUC, recall, precision, F1, balanced accuracy, calibration, bootstrap intervals
  ([`ml/experiment.py`](backend/ml/experiment.py), [model report](docs/ml/model-report.md))
- [x] **Metrics by group** (age band, booking channel, distance band) with intervals and small-group warnings
- [x] **One scikit-learn Pipeline artifact** (preprocessing + model in one file) with metadata
  ([`ml/artifacts/`](backend/ml/artifacts/))
- [x] **Reproducible training script** with fixed seeds and pinned dependencies; `--check` rebuilds and compares
  ([`ml/train.py`](backend/ml/train.py))
- [x] **Versioned inference endpoint** `POST /api/ml/v1/no-show/predict/` that validates the input schema, rejects
  malformed, out-of-range and unknown fields, and returns the prediction, probability and model version
- [x] **Dashboard card** on `/profile`, labelled as an educational demo, never medical advice
- [x] **Week 1 and Week 2 still work**: all 278 earlier backend tests and 24 frontend tests still pass
- [x] **Tests**: 151 new backend tests (429 in total) and 23 new frontend tests (47 in total)
- [x] **Trade-offs documented** (below)

### How it fits together

```
generate.py ──► appointments.csv ──► split (features.py) ──► analysis.py ──► eda.md
                                         │
                                         ▼
                              experiment.py (fit on train, choose on validation, test once)
                                         │                         └──► model-report.md + metrics.json
                                         ▼
                              train.py ──► noshow-1.0.0.joblib + noshow-1.0.0.json
                                                   │
                                                   ▼  SHA-256 checked before loading
              Dashboard card ──► POST /api/ml/v1/no-show/predict/ ──► predictor.py (loaded once)
```

| File in `backend/ml/` | What it does |
|---|---|
| `data/generate.py` | Seeded generator: invents appointments and decides `no_show` from a written rule plus noise |
| `features.py` | The input columns, the split, and the preprocessing (fill blanks, mark blanks, scale, one-hot) |
| `analysis.py` | Writes [`docs/ml/eda.md`](docs/ml/eda.md) from the training rows only |
| `models.py`, `evaluate.py`, `experiment.py` | The three models, the metrics and rules, and the experiment that writes the model report |
| `artifact.py`, `train.py` | Save and **checksum-verified** load of the model file; the reproducible training script |
| `serializers.py`, `predictor.py`, `views.py`, `urls.py` | The API: validation from the model's schema, loading once, the endpoint |

### Design choices and trade-offs (Week 3)

| Decision | Why | Trade-off |
|---|---|---|
| **Synthetic data from a rule we wrote, plus noise** | No real data is allowed; a written rule lets us know the best possible score (ROC-AUC 0.657) and catch leakage | The scores show that the method works; they say nothing about real clinics |
| **Split first** (70/15/15, stratified, seed 42); preprocessing inside the Pipeline | Fill-in values and scaling are learned from training rows only, so validation and test rows never leak in (tested) | One fixed split; the intervals show how much the numbers could move |
| **No class weights** | The API returns a probability, which should mean what it says; class weights would push every probability up | Class imbalance is handled by the threshold instead |
| **Threshold chosen on validation only** (best F1, ties go to the higher threshold), then frozen at **0.22** | The test rows play no part in any choice | F1 is a neutral choice for a demo; a real clinic would set it from the cost of each kind of mistake |
| **Test set used once**, after the model and every threshold were fixed | So the final numbers are an honest exam, not something we tuned towards | Only one look; no second chance on the same rows |
| **Logistic regression chosen over gradient boosting** | The rule was fixed in advance: the more complex model must beat logistic regression with a 95% bootstrap interval above zero. It did not (PR-AUC +0.016, interval −0.013 to +0.045) | Possibly a little performance left unused, in exchange for a simpler, explainable model that memorised less |
| **Leakage alarm**: stop if a model beats its pile's best possible score by more than **0.03**, or any ROC-AUC is above 0.90 | A score too good to be true usually means the answer leaked into the inputs. The margin allows for luck on a 900-row pile (the margin was suggested by Claude in a separate chat and approved by me) | A small leak could hide inside the margin |
| **Model fitted on the 4,200 training rows only** | The shipped file is exactly the one the model report describes | A production system would refit on all the data and re-derive the threshold |
| **Pickle hash check**: the model file's SHA-256 must equal `EXPECTED_SHA256` in reviewed code **before** it is unpickled | A `.joblib` file is a pickle, and loading a pickle can run code hidden inside it. The bytes are read once, checked, then loaded from memory, so the file cannot be swapped in between; the scikit-learn version must also match. `.gitattributes` marks `*.joblib` as binary so git never changes its bytes | The checksum proves "this is the file we built"; it does not make an untrusted pickle safe. Safer formats (skops, ONNX) would need new dependencies |
| **Dataset and model committed** | A clean clone works straight away; `python -m ml.train --check` proves the committed files are reproduced | A new model means a reviewed change to `EXPECTED_SHA256` |
| **Validation built from the model's metadata schema**; unknown fields rejected; whole numbers must be whole numbers | The API and the model cannot disagree about the inputs; nobody can smuggle in the answer column | Stricter than DRF's defaults (`"21"` and `21.0` are refused) |
| **Model loaded once, on the first request**; a failed load gives **503** and is not remembered | Fast after the first request; a fixed file works again without a restart; other routes keep working | The first request is slower |
| **Members only, with CSRF and a 30 per minute throttle**; nothing stored, audited or logged | The inputs are fictional and nothing changes, so there is nothing to audit (and no values may be logged) | No record of how the demo is used |
| **`v1` in the URL, `model_version` in the response** | The URL versions the request/response shape; a retrained model changes `model_version`, not the URL | Two version numbers to explain |
| **The card is hidden when the member has no profile** | It sits below the wellness card, which only exists once there is a profile. It stays usable on a deactivated profile, because it never uses profile data | A member must create a profile before trying the demo |
| `ml` is not in `INSTALLED_APPS`; the pickle refers to helpers in `ml.features` | No database models or commands are needed | The model file can only be loaded where the `ml` package exists |

### Metrics

**Final exam: the test rows (900, used once).** The threshold for each model was chosen on validation.

| Model | ROC-AUC | PR-AUC | Recall | Precision | F1 | Balanced accuracy |
|---|---|---|---|---|---|---|
| Baseline (everyone gets 20.8%) | 0.500 | 0.208 | 100.0% | 20.8% | 0.344 | 50.0% |
| **Logistic regression (chosen)** | **0.617** | **0.340** | **50.8%** | **29.5%** | **0.373** | **59.5%** |
| Gradient boosting | 0.620 | 0.316 | 46.5% | 29.4% | 0.360 | 58.6% |

In plain words: the chosen model catches about half of the fictional no-shows (95 of 187), and about 3 in 10 of its
flags are right. That is modest on purpose: even a model that knew the rule exactly could only reach ROC-AUC 0.639 on
these rows, because the noise and the final coin flip cannot be predicted.

**What the 0.22 cutoff means.** The 22% line is a decision threshold, chosen on the validation rows (best F1) and then
frozen. It is not a prediction that the person will miss: an estimate above it suggests an **extra reminder**, not a
certain no-show. On the 900 test rows the model flagged 322 fictional appointments. 95 of them were real no-shows
(precision 29.5%); the other 227 would get a reminder they did not need (false reminders). It caught 95 of the 187
no-shows (recall 50.8%), so 92 missed appointments would get no extra reminder (missed reminders). A lower line
catches more no-shows but sends more unneeded reminders; a higher line does the opposite. The card says the same
thing next to every result. Source: section 6 of the [model report](docs/ml/model-report.md).

| Comparison on validation (PR-AUC) | Difference | 95% interval | Clearly better? |
|---|---|---|---|
| Logistic regression vs baseline | +0.100 | +0.062 to +0.158 | yes |
| Gradient boosting vs baseline | +0.116 | +0.070 to +0.178 | yes |
| Gradient boosting vs logistic regression | +0.016 | −0.013 to +0.045 | **no**, so logistic regression was chosen |

The probabilities are honest: on the test rows, the predicted and actual no-show rates differ by at most 7.8 points in
any band of 90 rows. No leakage alarm went off (best possible ROC-AUC: validation 0.637, test 0.639).
All numbers: [docs/ml/model-report.md](docs/ml/model-report.md) and
[`backend/ml/reports/metrics.json`](backend/ml/reports/metrics.json).

### Dataset limits and bias

- **Synthetic, from rules we wrote.** Every group difference in the rule (for example +0.45 for age 18–24, +0.60 for
  over 30 km) is an **arbitrary choice** made to give the bias checks something to find. None of it is a claim about
  real people or populations.
- **Class imbalance**: 20.8% no-shows. "Everyone attends" would be 79.2% accurate and useless, so accuracy is not used
  to judge the models.
- **Small groups**: on the test rows, 65+ (79 rows) and over 30 km (96 rows) are marked "too small to judge"; in
  person (104 test rows, 93 validation rows) is only just above the limit, so its results are noisy too.
- **Missing values with a pattern**: distance is blank 13.8% of the time for phone bookings and 4.7% otherwise, so a
  blank partly means "booked by phone".
- **What the group check found** (test rows): the model raises false alarms for 44.9% of attended appointments 15–30 km
  away vs 24.2% for 5–15 km, and the intervals do not overlap. Both groups miss about 22% of the time, so the model is
  flagging people **because of their distance**, as the rule told it to. This is how bias in data becomes bias in a
  model. Differences by age band and booking channel were **not** clear (the intervals overlap).

Full details: [data card](docs/ml/data-card.md) and section 8 of the [model report](docs/ml/model-report.md).

### Run, reproduce and test (Week 3)

Install the pinned packages again after pulling (Week 3 adds scikit-learn, numpy, pandas and joblib):

```bash
cd backend
pip install -r requirements.txt

python -m ml.data.generate --seed 42 --rows 6000 --noise 1.0   # rebuild the dataset (identical file)
python -m ml.analysis                                           # rebuild docs/ml/eda.md
python -m ml.experiment                                         # rebuild the model report and metrics.json (~40 s)
python -m ml.train --check                                      # rebuild the model in memory and compare; writes nothing
python -m ml.train                                              # write the model files (then review EXPECTED_SHA256)

python -m pytest                    # 429 passed at the end of Week 3 (278 Week 1–2 + 151 Week 3); see "Tests" for today's count and time
ML_SKIP_SLOW=1 python -m pytest     # skips the 7 slow retraining tests locally (they run by default)
```

```bash
cd frontend
npm test       # 47 passed (24 Week 1–2 + 23 Week 3)
```

Then start both servers as in "Run it locally" below, sign in as a member, create a profile and use the
**No-show demo** card (or the side-menu link).

| New test file | What it proves |
|---|---|
| `test_ml_data.py` | The generator is reproducible; schema, ranges and missing values match the data card; no column leaks the answer; the noise setting works; the committed CSV is exactly what the generator makes |
| `test_ml_split.py` | The split is 70/15/15, stratified and reproducible; fill-in values and scaling come from training rows only; changing validation or test rows changes nothing learned |
| `test_ml_models.py` | Metrics and the threshold match hand calculations; the leakage alarm catches a planted copy of the answer; the selection rule; group counts; the committed report matches a fresh run |
| `test_ml_artifact.py` | A tampered model file is refused **before unpickling**; missing files and a different scikit-learn version are refused; the metadata is correct; retraining gives identical predictions |
| `test_ml_api.py` | Who may call the endpoint; every kind of bad input gives 400; nothing is echoed, logged or stored; the model loads once; 503 when it cannot load; the 30 per minute throttle; the Swagger docs |
| `frontend/tests/no-show-demo-card.test.tsx` | The request body (blank = `null`), the quick checks, server errors, the 401 / 403 / 429 / 503 messages, the keyboard path, the announced result, no medical wording, and the card's place on the page |

### Sample request and response (real output)

`POST /api/ml/v1/no-show/predict/` as a signed-in member (JWT cookie + `X-CSRFToken` header):

```json
{"lead_time_days": 21, "weekday": "mon", "hour": 9, "visit_type": "new_visit",
 "booking_channel": "online", "reminder_sent": "no", "prior_visits": 3,
 "prior_no_shows": 1, "distance_band": "15_30km", "age_band": null}
```

**200**:

```json
{"prediction": "likely_no_show", "probability": 0.5279, "threshold": 0.22,
 "model_version": "noshow-1.0.0",
 "disclaimer": "Educational demo trained on synthetic data. Not medical advice, not a diagnosis, and not a prediction about any real person or appointment."}
```

The same request with `lead_time_days: 120`, `weekday: "sunday"`, `hour` left out and an extra `no_show: 1` gives
**400**, naming every problem without repeating the values:

```json
{"error": {"code": "validation_error", "message": "Invalid input.",
  "fields": {"lead_time_days": ["Must be between 0 and 90."],
             "weekday": ["Must be one of: mon, tue, wed, thu, fri, sat."],
             "hour": ["This field is required."],
             "no_show": ["Unknown field."]},
  "request_id": "85e97f94-ce8f-4095-a240-3e63c548267c"}}
```

| Status | When |
|---|---|
| 200 | Valid input: prediction, probability, threshold, model version, disclaimer |
| 400 | Missing field, wrong type, out of range, value not allowed, unknown field, broken rule, or a body that is not a JSON object |
| 401 | Not signed in as a member (an admin session also gets 401, as on every member route) |
| 403 | Missing or invalid `X-CSRFToken` header |
| 429 | More than 30 requests a minute from the same member |
| 503 | `model_unavailable`: the checksum-verified model could not be loaded |

The server enforces each of these itself, not only the card. Six real responses (200, 400, 400 for an unknown `role`
field, 403 without the CSRF header, 401 signed out, 401 for an admin session), captured by a script over real HTTP, are in
[docs/evidence/week3.md](docs/evidence/week3.md#server-enforcement-mentor-review).

### Limitations and future work (Week 3)

- **Synthetic data only.** The model rediscovers rules we wrote; it is not evidence about real appointments.
- **One split and one seed**; the validation and test piles have 900 rows each, and small groups cannot be judged.
- **The threshold** maximises F1 on validation, a neutral demo choice, not one based on real costs.
- **The shipped model uses the training rows only**; production would refit on all the data and re-derive the
  threshold.
- **Pickle format**: protected by the checksum, but still a pickle. A safer format (skops or ONNX) is future work.
- **Future work: training without `age_band`** (and other group inputs) to measure what removing them costs in
  accuracy and how the group gaps change. It was left out of this week on purpose.

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
- [x] **Role-boundary tests**: 278 backend tests, including every route checked for member / admin / signed-out access
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
| ML (Week 3) | scikit-learn 1.9.1, pandas, numpy, joblib (exact pins in `requirements.txt`) | One Pipeline for preprocessing + model, reproducible with fixed seeds |
| Tests | pytest + pytest-django (+ freezegun); Vitest + Testing Library | 429 backend tests (278 Week 1–2 + 151 Week 3), 47 frontend tests (24 Week 1–2 + 23 Week 3) |

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
| `ml` (Week 3) | synthetic data generator, split and preprocessing, experiment and model report, checksum-verified model artifact, prediction endpoint (see "What is new in Week 3") |

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
| **A profile with contacts always has exactly one primary.** *At most one* is enforced **by the database** (partial unique index `contact_one_primary_per_profile`). *At least one* is enforced **only in the service**, under the profile row lock: the first contact becomes primary, deleting the primary promotes the oldest remaining contact, and `is_primary=false` on the current primary is **rejected with 400** (`"You need a primary contact. To change it, choose "Make primary" on another contact."`). The member moves the primary with "Make primary" on another contact, which switches both rows in one locked transaction. In the edit form the checkbox is locked while editing the current primary, with that hint | The member always chooses who their primary contact is; nothing is promoted behind their back except when the primary is deleted | *At least one* is application-level only: a raw SQL `UPDATE` could still leave a profile without a primary. Enforcing it in PostgreSQL would need a deferred constraint trigger, which we chose not to add |
| **Phones stored in one canonical form**: optional `+` then **7–15 digits** (`"+92 (300) 123-4567"` → `"+923001234567"`), normalised by `profiles/phones.py` before validation, storage and the duplicate check; CHECK constraint `contact_phone_is_canonical` as backstop | Punctuation can no longer hide a non-number (`1------` is rejected) or a duplicate (`+92-300-123-4567` = `+92 300 1234567`), and the `(profile, phone)` unique constraint now catches equivalent formats too | No country rules without a new dependency: `0300 1234567` and `+92 300 1234567` (or `92…` and `+92…`) are still different numbers. Members see the compact canonical form |
| **Deactivated profile is read-only** (403 + a `denied` audit event) | Admins can freeze a profile without deleting data | Owner cannot fix their data until reactivated |
| **One locking policy for every profile change**: member writes *and* admin deactivate / reactivate first lock the profile row (`SELECT … FOR UPDATE`) and decide from that locked, fresh row. Member services re-check `status` in `services._lock()`; the early check in the view is only a fast path | No member write can commit after a deactivation has committed: a request that waited for the lock re-reads the row and gets the same 403. Two admins cannot both record a status change. Same lock, same order everywhere, so no deadlocks | Writes to one profile queue behind each other (they are short). If the re-check refuses a write, the change rolls back first and the `denied` event is written afterwards (best-effort), so the rollback cannot undo it |
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
python -m pytest        # 658 passed (278 Week 1–2 + 151 Week 3 + 229 Week 4), about 4 to 7 minutes on this laptop (final run: 7 min 12 s; other Week 4 runs 3 min 23 s to 6 min 26 s);
                        # the Week 3 and Week 4 test files are listed under "What is new in Week 3" / "Week 4"
```

| File | What it proves |
|---|---|
| `test_models_week2.py` | every `IntegrityError` constraint, completion rules (0% / 25% / 100% / back to 75%), and the Week 1 → Week 2 data migration |
| `test_profiles.py` | 401 on every member route, own-data-only, 409 on a second profile, profile `DELETE`, deactivated profile = read-only (403 + audited), CSRF required on every write |
| `test_profile_sections.py` | demographics and wellness: PUT replace vs PATCH, validation (future / ancient date of birth, bad choices, ranges), goals replaced atomically |
| `test_emergency_contacts.py` | CRUD, max 3, primary rule, duplicate phone, **member A cannot read, edit or delete member B's contact (404)** |
| `test_primary_contact.py` | unsetting the current primary (also the only contact) → 400 with a clear message and nothing saved; editing the primary while keeping it primary works; and the **invariant test**: create, create-as-primary, "Make primary", refused unset, delete primary, delete down to zero, start again, checking **after every step** that a profile with contacts has exactly one primary (and an empty one has none) |
| `test_concurrency.py` | **PostgreSQL, two real connections in threads**, paused at exact lines with events (no sleep-based timing) and lock waits confirmed through `pg_stat_activity`: deactivation before the member takes the lock (PATCH, contact POST, profile DELETE) → 403 + committed `denied` event; member waiting on the admin's lock → 403; admin waiting on the member's lock → member's 200 counts; two admins → only one status change recorded; a contact made primary, or deleted, between the view's read and the lock → the delete re-reads it under the lock and still hands the primary on, and a delete or PATCH of a contact deleted meanwhile → 404, no event. Cleanup always releases, joins and closes, and checks no connection or lock is left |
| `test_phone_normalisation.py` | punctuation-heavy input (`1------`), the 7 / 15 digit boundaries, canonical storage, equivalent formats as duplicates on POST and PATCH, the fourth-contact limit in any format, the database CHECK, and migration 0007 (rewrites rows; stops on unsafe rows naming ids only) |
| `test_audit.py` | exactly one event per write, no secrets or values in any audit field, append-only, request id on every response and in the audit row, member activity |
| `test_audit_durability.py` | failure injection: when the required audit insert fails, every member write, profile deletion and admin deactivate / reactivate returns 503 `audit_unavailable` and rolls back completely (data, stored completion, no audit row) |
| `test_admin.py`, `test_admin_week2.py` | admin session list / search / detail, every filter and ordering, invalid values → 400, deactivate / reactivate with CSRF, login throttle, audit endpoints, **a member JWT gets 403 on every admin route and an admin session cannot use member routes** |
| `test_sensitive_fields.py` | admin responses lack date of birth, allergies, lifestyle notes and full phones; no response anywhere contains password, token or session data |
| `test_jwt.py`, `test_signup.py` | Week 1 auth: expiry, tampering, blacklisting, hashing, role injection ignored |

```bash
cd frontend
npm test                # 80 passed (Vitest + Testing Library, jsdom); 23 are the Week 3 card tests, 33 the Week 4 /ml tests
```

| File | What it proves |
|---|---|
| `tests/ConfirmDialog.test.tsx` | the confirm dialog's keyboard behaviour: focus starts on Cancel (or on the type-to-confirm box), Tab / Shift+Tab stay inside, Escape closes but not while busy (focus then stays on the dialog box), focus returns to the opener, or to a fallback when the opener is gone or disabled |
| `tests/admin-page.test.tsx` | where focus lands on the admin page after a deactivate or reactivate: the selected profile's heading if it is still listed, otherwise the "Member profiles" heading (e.g. when the Active filter loses its last match) |
| `tests/contacts-card.test.tsx` | after deleting an emergency contact and reloading the list, focus lands on the "Emergency contacts" heading, not on the page body; editing the current primary shows the primary checkbox ticked, **disabled** and described by the hint; a non-primary contact's checkbox stays usable; an `is_primary` error from the server is shown under the checkbox |
| `tests/validation.test.ts` | the contact form's phone check uses the server's rule: `1------`, `((((1))))`, letters and a `+` in the middle are rejected; 6 and 16 digits rejected; 7 and 15 digits accepted |
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
| POST | `/api/ml/v1/no-show/predict/` | JWT + CSRF (throttled 30/min) | Week 3 educational demo: no-show chance for a fictional appointment; uses no profile data |

A deactivated profile can be read (200) but every write and `DELETE` returns 403. (The Week 3 demo endpoint does not
touch the profile, so it still works for a deactivated profile.)

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
| `pytest-week2.png` | Terminal: `python -m pytest` → **224 passed**. This is the original Week 2 run, before the review fixes; the final counts (278 backend, 24 frontend) and the tested commit are in [docs/evidence/week2-review.md](docs/evidence/week2-review.md) and the PR #3 conversation |

### Week 3

| | |
|---|---|
| ![Demo card with a result](docs/screenshots/week3/card-result.png) | ![Swagger request](docs/screenshots/week3/swagger-request.png) |
| The demo card after "Check this example" on the prefilled fictional appointment: "52.8% chance this fictional appointment is missed", a bar, "Above the 22% line: this suggests an extra reminder, not a certain no-show.", the model version and the disclaimer | Swagger: the *ml demo (educational)* endpoint, its disclaimer and the request example |
| ![Swagger responses](docs/screenshots/week3/swagger-responses.png) | ![Quick check, light](docs/screenshots/week3/card-light.png) |
| Swagger: the real 200 example and what 400, 401, 403, 429 and 503 mean | The card's quick check in light mode: 91 days is refused before anything is sent ("Enter a whole number from 0 to 90.") |
| ![Quick check, dark](docs/screenshots/week3/card-dark.png) | |
| The same quick check in dark mode | |

### Week 4

Captured on 10 November 2026 with headless Chrome at 2x scale, against the real local model (`llama3.2:3b` +
`nomic-embed-text`), using throwaway fictional accounts that were deleted afterwards.

| | |
|---|---|
| ![Supervised tab](docs/screenshots/week4/supervised.png) | ![Clusters tab](docs/screenshots/week4/clusters.png) |
| `supervised.png`: the Supervised tab: versions, the four models on validation, the choice and why, the confusion matrix at 0.22, importance, the overfitting gap, the mistakes, and the test pile shown once | `clusters.png`: the Clusters tab, labelled exploratory: elbow and silhouette, k = 2 with the weak-structure note, the 500-point PCA view (circles and squares), the descriptions and the agreement |
| ![FAQ answered](docs/screenshots/week4/faq-answered.png) | ![FAQ insufficient](docs/screenshots/week4/faq-insufficient.png) |
| `faq-answered.png`: a real answer with its verified citation from the *Emergency contacts* policy, 706 + 54 tokens, cost 0.00, `llama3.2:3b (ollama)`, 73.8 s (cold) | `faq-insufficient.png`: "What is the capital of France?" gives the fixed insufficient-information answer; the model was not called |
| ![FAQ refused](docs/screenshots/week4/faq-refused-email.png) | ![Admin upload refuses a pdf](docs/screenshots/week4/admin-upload-refused-pdf.png) |
| `faq-refused-email.png`: a question with an email address is refused before anything is sent | `admin-upload-refused-pdf.png`: an admin's upload panel refuses a `.pdf` ("Only .txt or .md files can be uploaded.") |
| ![Swagger](docs/screenshots/week4/swagger-week4.png) | |
| `swagger-week4.png`: Swagger with the new *llm faq (educational)* group and the two Week 4 report endpoints | |

## Review response (PR #3)

Mentor review of PR #3 at `9784e4d`. Each code point was fixed in its own commit on this branch, with tests that fail
on the previous commit and pass on the fix. Real output: [docs/evidence/week2-review.md](docs/evidence/week2-review.md).

| Review point | What changed | Commit | Proof |
|---|---|---|---|
| **1. Audit durability** | The change, the completion update and the **required** audit event commit in one transaction; a failed required audit rolls everything back and returns 503 `audit_unavailable`. Logins, views and denied attempts stay best-effort (see "Required vs best-effort audit events") | `6a5633f` | `test_audit_durability.py`: failure injection for every member write, **profile deletion** and admin deactivate / reactivate, including a real PostgreSQL rejection |
| **2. Phone normalisation** | One canonical form (`+` then 7–15 digits) before validation, storage and duplicate checks; data migration `0007`; CHECK constraint `0008` | `15f7b1b` | `test_phone_normalisation.py` (punctuation-heavy input, equivalent formats on POST and PATCH, fourth-contact limit, DB CHECK, migration); catalog diff shows no other constraint changed |
| **3. Permission re-check after the lock** | Every profile change, member or admin, locks the profile row first and decides from that fresh row; a deactivation that committed while the request waited gives 403, and the `denied` event is written after the rollback so it is kept. The contact-limit lock is unchanged | `b8dd91a` | `test_concurrency.py`: PostgreSQL, two real connections, paused with events (no sleeps), 20 / 20 consecutive runs |
| **4. Primary contact** | A profile with contacts always has exactly one primary: unsetting the current primary returns 400; the edit form locks that checkbox with a hint. *At most one* by the database, *at least one* by the service | `3c58e99` | `test_primary_contact.py` invariant test checks the rule after every step; `contacts-card.test.tsx` |
| **5. Evidence and handoff** | Catalog check and a raw-SQL second primary rejected after the migrations (also on a database migrated from zero); overlap with Week 1 PR #2 checked by a throwaway merge (not merged); limits stated; final validation. Also: the frontend phone check now uses the server's rule (`40cb5ab`) | `40cb5ab` + this docs commit | `docs/evidence/week2-review.md`, [docs/ai-workflow.md](docs/ai-workflow.md) "Week 2 review response" |
| **Follow-up (from the Week 3 PR review): contact deletion race** | `delete_contact` re-reads the contact by id and owner **under the profile lock**, so a contact made primary after the view read it still hands the primary on; a contact deleted meanwhile gives 404 and writes no event. The same 404 now replaces a 500 when a PATCH loses the race to a delete (`update_contact` already re-read under the lock, but nothing caught "gone") | follow-up commit (hash in the PR #3 conversation) | `test_concurrency.py` E, F, G: fail on `96e29a2`, pass on the fix; checks one primary, completion and field-names-only audit events; 20 / 20 consecutive runs (evidence file §6) |

**Week 1 PR #2 overlap.** PR #2 is not merged. A throwaway merge into this branch gave 10 conflicts; in every one this
branch already has its own later version of the same Week 1 fix, so each resolves to this branch's file, and the merged
result passed every check (details in the evidence file). Two ways to finish, for the mentor to choose: merge PR #2
into `main` first and then update PR #3 from `main` with that resolution, or close PR #2 as superseded by PR #3.

**Loom points.** These are about the recording; the evidence to show is listed next to each.

| Loom point | What to show | Where it is |
|---|---|---|
| 00:44–02:34 completion | The four 25% conditions (demographics, at least one contact, wellness preferences, at least one goal) and one section changing both its data and the stored completion | `test_four_sections_reach_100_complete`; `test_models_week2.py` completion rules; the stored completion rolling back in `test_audit_durability.py` |
| 02:51–05:22 history vs masking | The member's activity stores field names only; the admin detail is an allow-list that shows some fields and masks others | `test_no_audit_field_contains_secrets_or_values`; `test_admin_detail_hides_sensitive_fields_and_masks_phones`; `adminpanel/serializers.py` |
| 05:34–06:49 keyboard | Focus returning to the heading after the row disappears, and what the test asserts | `frontend/tests/admin-page.test.tsx`, `frontend/tests/contacts-card.test.tsx` |
| 07:18–10:26 one request traced | serializer → `write_transaction` → `services._lock` (re-check) → `recalculate_completion` → `record_event`; the repaired database rule | `profiles/views.py`, `profiles/services.py`; evidence file §1 (second primary rejected) |
| 10:34–11:39 auth | Access-token expiry separately from CSRF; a member request denied at an admin endpoint | `test_expired_access_token_returns_401`; `test_member_login_without_csrf_token_is_rejected_and_sets_no_cookies`; `test_member_jwt_gets_403_on_every_admin_route` |
| 11:39–12:47 verification | Readable test summaries with the commands and the tested commit; the new audit-failure and concurrency checks; one prompt → reviewed diff → human correction | evidence file; [docs/ai-workflow.md](docs/ai-workflow.md) "Week 2 review response" |
| Length over 13 minutes | One 5–10 minute walkthrough | Recording edit (not a code change) |

## AI workflow

How AI was used to plan, build, review and debug this project, including prompt iterations, blast radius
control, a manual security review and a bug story: see [docs/ai-workflow.md](docs/ai-workflow.md).
The rules the AI must follow in this repo are in [CLAUDE.md](CLAUDE.md).
Week 3 has its own section there ("Week 3: Machine Learning Pipeline and Prediction API"): every prompt I sent, which
ones were drafted with help from Claude in a separate chat, my decisions, and what the checks caught.
Week 4 has its own section too ("Week 4: Comparative ML Workbench, Clustering, LLM Endpoint and FAQ Assistant"),
starting with a short summary.

## Demo video

Week 1: https://www.loom.com/share/7f3a96d221f1415b9c2abe2070b3f38e

Week 2: https://www.loom.com/share/5d16ef5c30ba4496a1de8ce16270edba

Week 3: https://www.loom.com/share/9d6433ae55664ab89026f9e7df4299b4

## Limitations

* Intended for local development: set `DEBUG=False` and HTTPS for production (cookies then become `Secure`).
* **Audit append-only is application-level only.** The ORM guards (model `save()` / `delete()` and queryset
  `update()` / `delete()` raise `AppendOnlyError`) and the lack of any API route protect the audit log from the
  application's own code. They do **not** protect it from direct database access: raw SQL, `psql`, a superuser or a
  migration can still update or delete audit rows (shown in the evidence file). Direct database access needs its own
  restrictions, for example an application database role without `UPDATE` / `DELETE` on `audit_auditevent`, or triggers.
* **"At least one primary contact" is enforced only in the service** (under the profile row lock). The database enforces
  "at most one" (partial unique index), but a raw SQL `UPDATE` can still leave a profile with contacts and no primary.
* **Phone numbers have no country rules** (that would need a new dependency): `0300 1234567` and `+92 300 1234567`, or
  `92…` and `+92…`, count as different numbers.
* **Required audit events fail closed**: if the audit table cannot be written, member edits and admin status changes
  are refused with 503 `audit_unavailable` until it can.
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
* **Week 3 ML demo**: synthetic data only, one split and one seed, a pickle model file protected by a checksum, and
  the model fitted on training rows only. See "Limitations and future work (Week 3)" above.
* **Week 4 workbench: the test pile was reused.** The test pile was already used in Week 3 to report the
  baseline, logistic regression and gradient boosting, so it is no longer completely unseen. In Week 4 every model
  comparison and every choice is made on the validation pile only; the test numbers (including random forest's)
  are reported afterwards and are not used to choose. The workbench ships no model: the API still uses
  `noshow-1.0.0`. See [docs/ml/workbench-report.md](docs/ml/workbench-report.md).
