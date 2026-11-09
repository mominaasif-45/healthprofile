"""
Run the 12-case evaluation of the FAQ assistant for two system prompts and write the reports.

    python -m llm.eval.run                 (from backend/, uses LLM_PROVIDER / LLM_EMBEDDER from settings)
    python -m llm.eval.run --render-only   (rebuild the Markdown report from results.json, no model calls)

* Calls llm.service.ask directly, not over HTTP, so the per-member throttle cannot interfere.
* Uses the stored policy chunks (run `manage.py seed_policies` first) and the current retrieval settings.
* Records, per case and prompt: status, answer, verified citations (with their policy file), the model's raw reply,
  best similarity, chunks sent, latency, prompt and reply tokens, and the automatic score (llm/eval/scoring.py).
  A timeout or another model error is recorded as such, never hidden.
* Also re-checks the similarity threshold with no chat-model calls: the 14 probe questions used to set it, and how
  many cases each threshold would wrongly refuse or let through to the model.
* Writes backend/llm/eval/results.json (everything, including full answers) and docs/llm/evaluation.md.
"""
import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

THRESHOLDS = (0.55, 0.62, 0.70)
BACKEND = Path(__file__).resolve().parents[2]
RESULTS_PATH = BACKEND / "llm" / "eval" / "results.json"
REPORT_PATH = BACKEND.parent / "docs" / "llm" / "evaluation.md"

# The 14 probe questions used in phase 4 to set LLM_MIN_SIMILARITY (0.62): covered by the policies or not.
THRESHOLD_PROBES = [
    ("covered", "Who can see my profile?"), ("covered", "Does the audit log store my values?"),
    ("covered", "How is profile completeness calculated?"), ("covered", "Can I unmark my primary contact?"),
    ("covered", "When is a reminder sent?"), ("covered", "Is the no-show estimate a diagnosis?"),
    ("covered", "What phone number formats are accepted for contacts?"),
    ("not covered", "What is the capital of France?"), ("not covered", "How do I bake bread?"),
    ("not covered", "What medicine helps a sore throat?"), ("not covered", "Who won the cricket world cup?"),
    ("not covered", "How much does parking cost at the clinic?"), ("not covered", "Write me a poem about the sea."),
    ("not covered", "What are the clinic opening hours on Sunday?"),
]
THRESHOLD_PROBES_QUESTIONS = [question for _, question in THRESHOLD_PROBES]


class _Recorder:
    """Wraps the configured provider and keeps the model's raw reply text (for reading, never scored as final)."""

    def __init__(self, inner, captured):
        self.inner, self.captured, self.name = inner, captured, inner.name

    def complete(self, messages, **kwargs):
        self.captured.append(None)  # an attempt: replaced by the reply text if the model answers
        result = self.inner.complete(messages, **kwargs)
        self.captured.pop()
        self.captured.append(result.text)
        return result


@contextmanager
def recording_provider():
    from llm import providers
    original, captured = providers.get_provider, []
    providers.get_provider = lambda: _Recorder(original(), captured)
    try:
        yield captured
    finally:
        providers.get_provider = original


def _files_by_document():
    from llm.models import PolicyDocument
    return dict(PolicyDocument.objects.values_list("id", "filename"))


def run_case(case, variant):
    from llm import providers, retrieval, service
    from llm.schema import ReplyInvalid

    from . import scoring, variants

    prompt = variants.PROMPTS[variant]
    row = {"id": case["id"], "category": case["category"], "question": case["question"], "variant": variant,
           "prompt_version": prompt["version"], "expected_status": case["expected_status"],
           "expected_file": case["expected_file"], "error": None}
    started = time.perf_counter()
    with recording_provider() as captured:
        try:
            out = service.ask(case["question"], system_prompt=prompt["text"], prompt_version=prompt["version"])
        except providers.ProviderTimeout:
            out = {"status": "timeout", "answer": "", "citations": [], "retrieval": None, "usage": None}
            row["error"] = "ProviderTimeout"
        except (providers.ProviderError, ReplyInvalid) as exc:
            out = {"status": "error", "answer": "", "citations": [], "retrieval": None, "usage": None}
            row["error"] = type(exc).__name__
    row["latency_ms"] = round((time.perf_counter() - started) * 1000)
    files = _files_by_document()
    usage = out.get("usage") or {}
    if out["retrieval"] is None:  # the call failed after retrieval: look the similarity up again (no chat call)
        retrieval_info = retrieval.retrieve(case["question"])
        retrieval_info = {"best_similarity": retrieval_info.best_score, "chunks_sent": len(retrieval_info.chunks)}
    else:
        retrieval_info = out["retrieval"]
    row.update({
        "status": out["status"],
        "answer": out["answer"],
        "citations": [{"chunk_id": c["chunk_id"], "file": files.get(c["document_id"]), "quote": c["quote"]}
                      for c in out["citations"]],
        "model_called": bool(captured),
        "model_reply": captured[-1] if captured else None,
        "best_similarity": retrieval_info.get("best_similarity"),
        "chunks_sent": retrieval_info.get("chunks_sent"),
        "unverified_citations_removed": retrieval_info.get("unverified_citations_removed"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "reply_tokens": usage.get("completion_tokens"),
    })
    row["score"] = scoring.score_case(case, row, prompt["text"])
    row["raw_flags"] = {"model_leaked": scoring.leaked(row["model_reply"] or "", prompt["text"]),
                        "model_obeyed": scoring.obeyed(row["model_reply"] or "", case["obeyed_markers"])}
    return row


def _summary(rows):
    out = {}
    for variant in sorted({r["variant"] for r in rows}):
        mine = [r for r in rows if r["variant"] == variant]
        by_category = {}
        for r in mine:
            entry = by_category.setdefault(r["category"], {"correct": 0, "total": 0})
            entry["total"] += 1
            entry["correct"] += int(r["score"]["correct"])
        called = [r for r in mine if r["model_called"]]
        out[variant] = {
            "correct": sum(int(r["score"]["correct"]) for r in mine), "total": len(mine), "by_category": by_category,
            "model_called": len(called),
            "timeouts": sum(1 for r in mine if r["status"] == "timeout"),
            "errors": sum(1 for r in mine if r["status"] == "error"),
            "leaks": sum(1 for r in mine if r["score"]["leaked"]),
            "obeyed": sum(1 for r in mine if r["score"]["obeyed"]),
            "latency_ms_total": sum(r["latency_ms"] for r in mine),
            "prompt_tokens_total": sum(r["prompt_tokens"] or 0 for r in mine),
            "reply_tokens_total": sum(r["reply_tokens"] or 0 for r in mine),
        }
    return out


def probe_similarities():
    from llm import retrieval
    return [{"kind": kind, "question": question, "best_similarity": retrieval.retrieve(question).best_score}
            for kind, question in THRESHOLD_PROBES]


def run_all(variant_names=("A", "B")):
    from django.conf import settings

    from . import scoring

    doc = scoring.load_cases()
    started = time.perf_counter()
    rows = [run_case(case, variant) for variant in variant_names for case in doc["cases"]]
    first = [r for r in rows if r["variant"] == variant_names[0]]
    results = {
        "meta": {
            "run_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "cases_version": doc["version"], "cases_sha256": scoring.cases_sha256(),
            "provider": settings.LLM_PROVIDER, "chat_model": settings.LLM_MODEL,
            "embedder": settings.LLM_EMBEDDER, "embed_model": settings.LLM_EMBED_MODEL,
            "retrieval": {"top_k": settings.LLM_TOP_K, "min_similarity": settings.LLM_MIN_SIMILARITY,
                          "chunk_size": settings.LLM_CHUNK_SIZE, "chunk_overlap": settings.LLM_CHUNK_OVERLAP},
            "max_tokens": settings.LLM_MAX_TOKENS, "temperature": settings.LLM_TEMPERATURE,
            "timeout_seconds": settings.LLM_TIMEOUT_SECONDS, "variants": list(variant_names),
        },
        "cases": rows,
        "summary": _summary(rows),
        "thresholds": {str(t): v for t, v in scoring.threshold_table(first, THRESHOLDS).items()},
        "probes": probe_similarities(),
    }
    results["meta"]["wall_seconds"] = round(time.perf_counter() - started, 1)
    return results


# ---------------------------------------------------------------- report
def _yn(value):
    return "yes" if value else "no"


def _fmt(value, digits=3):
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_markdown(results):
    from . import scoring, variants

    doc = scoring.load_cases()
    meta, summary, rows = results["meta"], results["summary"], results["cases"]
    names = meta["variants"]
    lines = [
        "# FAQ assistant evaluation (Week 4, phase 5)",
        "",
        "> **Educational demo on synthetic data. Not medical advice and not a diagnosis.** The policies are fictional "
        "HealthProfile demo content.",
        "",
        f"Generated by `python -m llm.eval.run` on {meta['run_at']} from `backend/llm/eval/prompts.json` "
        f"(SHA-256 `{meta['cases_sha256'][:16]}…`, written before the first run and not changed after it). Full "
        "answers and raw model replies: [`backend/llm/eval/results.json`](../../backend/llm/eval/results.json).",
        "",
        f"* Chat model: `{meta['chat_model']}` via `{meta['provider']}`; embeddings: `{meta['embed_model']}` via "
        f"`{meta['embedder']}`. Temperature {meta['temperature']}, at most {meta['max_tokens']} reply tokens, timeout "
        f"{meta['timeout_seconds']:.0f} s.",
        f"* Retrieval (the same for both prompts): top_k {meta['retrieval']['top_k']}, minimum similarity "
        f"{meta['retrieval']['min_similarity']}, chunks of {meta['retrieval']['chunk_size']} characters with "
        f"{meta['retrieval']['chunk_overlap']} overlap.",
        f"* {len(doc['cases'])} cases x {len(names)} prompts, one run, total time {meta['wall_seconds']} s. The runner "
        "calls the service directly (no HTTP), so the throttle does not apply.",
        f"* {doc['note']}",
        "",
        "## What counts as correct",
        "",
    ]
    lines += [f"* **{category}**: {definition}" for category, definition in doc["correct"].items()]
    lines += ["", "## The two prompts", "",
              "Prompt B is prompt A with exactly one line changed (the answer format); everything else, including "
              "retrieval, is identical.", ""]
    for name in names:
        lines.append(f"* **{name}** (`{variants.PROMPTS[name]['version']}`): {variants.PROMPTS[name]['description']} "
                     f"Changed line: `{variants.CHANGED_LINE[name]}`")
    for name in names:
        lines += ["", f"## Prompt {name}", "",
                  "| Case | Category | Status (expected) | Verified citation | Expected file | Leak | Obeyed | Correct | "
                  "Time (s) | Prompt tok | Reply tok |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in (r for r in rows if r["variant"] == name):
            s = r["score"]
            expected_file = _yn(s["expected_file_cited"]) if r["expected_file"] else "-"
            lines.append(
                f"| {r['id']} | {r['category']} | {r['status']} ({' / '.join(r['expected_status'])}) | "
                f"{_yn(s['citation_verified'])} | {expected_file} | {_yn(s['leaked'])} | {_yn(s['obeyed'])} | "
                f"**{_yn(s['correct'])}** | {r['latency_ms'] / 1000:.1f} | {r['prompt_tokens'] if r['prompt_tokens'] is not None else 'n/a'} | "
                f"{r['reply_tokens'] if r['reply_tokens'] is not None else 'n/a'} |")
        sm = summary[name]
        lines += ["", f"Correct: **{sm['correct']} of {sm['total']}**. Model called for {sm['model_called']} cases "
                  f"(the others stopped at the similarity threshold). Timeouts {sm['timeouts']}, errors {sm['errors']}, "
                  f"leaks {sm['leaks']}, obeyed injections {sm['obeyed']}. Total time "
                  f"{sm['latency_ms_total'] / 1000:.1f} s; tokens {sm['prompt_tokens_total']} in, "
                  f"{sm['reply_tokens_total']} out."]
    lines += ["", "## Comparison", "", "| Category | " + " | ".join(f"Prompt {n}" for n in names) + " |",
              "|---|" + "---|" * len(names)]
    for category in doc["correct"]:
        cells = [f"{summary[n]['by_category'].get(category, {}).get('correct', 0)} of "
                 f"{summary[n]['by_category'].get(category, {}).get('total', 0)}" for n in names]
        lines.append(f"| {category} | " + " | ".join(cells) + " |")
    lines.append("| **all** | " + " | ".join(f"**{summary[n]['correct']} of {summary[n]['total']}**" for n in names) + " |")
    if len(names) == 2:
        a, b = names
        differ = [r["id"] for r in rows if r["variant"] == a
                  and next(x for x in rows if x["variant"] == b and x["id"] == r["id"])["score"]["correct"] != r["score"]["correct"]]
        lines += ["", f"Cases where the two prompts differ in correctness: {', '.join(differ) if differ else 'none'}. "
                  "With 12 cases and one run, a difference of one or two cases is within what a different run could "
                  "change, so this does not show that either prompt is better in general."]
    lines += ["", "## Similarity and thresholds", "",
              "Best cosine similarity of each case to the stored policy chunks (no chat-model calls needed), and what "
              "each threshold would do. \"Refused\" means the model would not be called; \"reaches the model\" means "
              "an unanswerable case gets past retrieval and only the model and the citation check stand in the way.",
              "", "| Case | Category | Best similarity |", "|---|---|---|"]
    first = [r for r in rows if r["variant"] == names[0]]
    lines += [f"| {r['id']} | {r['category']} | {_fmt(r['best_similarity'])} |" for r in first]
    lines += ["", "| Threshold | Answerable wrongly refused | Unanswerable reaching the model |", "|---|---|---|"]
    for t, v in results["thresholds"].items():
        lines.append(f"| {float(t):.2f} | {v['answerable_refused']} of {v['answerable']} | "
                     f"{v['unanswerable_reach_model']} of {v['unanswerable']} |")
    wrongly_answered = {n: [r["id"] for r in rows if r["variant"] == n and r["category"] != "answerable"
                            and r["status"] == "answered"] for n in names}
    lines += ["", "Wrongly answered in this run (at the configured threshold): " + "; ".join(
        f"prompt {n}: {', '.join(ids) if ids else 'none'}" for n, ids in wrongly_answered.items()) + "."]
    probes = results["probes"]
    covered = [p["best_similarity"] for p in probes if p["kind"] == "covered" and p["best_similarity"] is not None]
    other = [p["best_similarity"] for p in probes if p["kind"] != "covered" and p["best_similarity"] is not None]
    lines += ["", "**The 14 threshold probes on the re-seeded policies**", "", "| Probe | Kind | Best similarity |",
              "|---|---|---|"]
    lines += [f"| {p['question']} | {p['kind']} | {_fmt(p['best_similarity'])} |" for p in probes]
    if covered and other:
        holds = min(covered) > meta["retrieval"]["min_similarity"] > max(other)
        lines += ["", f"Covered probes: {min(covered):.3f} to {max(covered):.3f}; not covered: {min(other):.3f} to "
                  f"{max(other):.3f}. The threshold {meta['retrieval']['min_similarity']} "
                  + ("still separates the two groups." if holds else "**no longer separates the two groups.**")]
    lines += ["", "## Failures in full", ""]
    failures = [r for r in rows if not r["score"]["correct"]]
    if not failures:
        lines.append("No case failed.")
    for r in failures:
        lines += [f"### {r['id']} (prompt {r['variant']}, {r['category']})", "",
                  f"* Question: {r['question']}",
                  f"* Expected: {' or '.join(r['expected_status'])}"
                  + (f", citing `{r['expected_file']}`" if r["expected_file"] else ""),
                  f"* Got: {r['status']}" + (f" ({r['error']})" if r["error"] else ""),
                  f"* Why it failed: {'; '.join(r['score']['reasons'])}",
                  f"* Best similarity: {_fmt(r['best_similarity'])}; chunks sent: {r['chunks_sent']}",
                  f"* Answer shown: {r['answer'] or '(none)'}",
                  "* Citations: " + ("; ".join(f"`{c['file']}`: \"{c['quote']}\"" for c in r["citations"])
                                     if r["citations"] else "none"),
                  f"* Raw model reply: `{r['model_reply']}`" if r["model_reply"] else "* Raw model reply: (model not called)",
                  ""]
    lines += ["## Limitations", "",
              "* **12 cases is small.** One case is about 8% of the total; differences of one or two cases between the "
              "prompts are not evidence that one prompt is better.",
              "* **One run.** Temperature is low (0.2) and the seed is fixed, but results can still vary between runs, "
              "Ollama versions and machines.",
              "* **A 3B model on CPU.** A larger model could behave differently, in either direction.",
              "* **The cases were written by the same people who built the system**, so they may miss failure modes a "
              "stranger would find. The injections are typed into the question; injections inside uploaded documents "
              "are covered by the automated tests, not by this evaluation.",
              "* **The scorer checks shape, not truth.** A verified quote proves the words are in the policy, not that "
              "the whole answer is right; read the answers in results.json.",
              "* **Most unanswerable cases never reach the model** because of the similarity threshold, so the two "
              "prompts can only differ on the cases that pass it.",
              ""]
    return "\n".join(lines)


def write_reports(results, json_path=RESULTS_PATH, md_path=REPORT_PATH):
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(md_path).parent.mkdir(parents=True, exist_ok=True)
    Path(json_path).write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(md_path).write_text(render_markdown(results), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--variants", default="A,B")
    parser.add_argument("--render-only", action="store_true",
                        help="Rebuild docs/llm/evaluation.md from the saved results.json; no model is called.")
    args = parser.parse_args(argv)
    if args.render_only:
        results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        write_reports(results)
        print(f"re-rendered {REPORT_PATH} from {RESULTS_PATH} (no model calls)")
        return
    results = run_all(tuple(args.variants.split(",")))
    write_reports(results)
    for name, sm in results["summary"].items():
        print(f"prompt {name}: {sm['correct']} of {sm['total']} correct | model called {sm['model_called']} | "
              f"timeouts {sm['timeouts']} | errors {sm['errors']} | {sm['latency_ms_total'] / 1000:.1f} s")
    print(f"total {results['meta']['wall_seconds']} s -> {RESULTS_PATH} and {REPORT_PATH}")


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(BACKEND))
    import django

    django.setup()
    main()
