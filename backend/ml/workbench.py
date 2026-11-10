"""
Week 4, phase 1: the supervised comparison workbench.

Compares the baseline, logistic regression, random forest and gradient boosting on the Week 3 split with the
Week 3 preprocessing, and writes a report. It ships NO model: the API keeps serving noshow-1.0.0.

Order of work (the same rules as Week 3):
1. split first; every model is one Pipeline fitted on the training pile only (tuning by cross-validation
   inside the training pile, preprocessing refitted inside every fold);
2. compare on the validation pile, and make every choice there (each model's threshold, the "best" model
   whose mistakes we inspect);
3. only then score the test pile, at the thresholds frozen on validation, for the record. The test pile was
   already used in Week 3, so it is reported, never used to choose.

Writes docs/ml/workbench-report.md and backend/ml/reports/workbench.json. Run from backend/ (one CPU core,
a few minutes):

    python -m ml.workbench
"""
import json
from pathlib import Path

import numpy as np
import sklearn
from sklearn.base import clone
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_validate

from ml import evaluate, features, models
from ml.data import generate as gen
from ml.experiment import _rounded

VERSION = "workbench-1.0.0"
RESULTS_PATH = Path(__file__).resolve().parent / "reports" / "workbench.json"
REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "ml" / "workbench-report.md"
OVERFIT_GAP = 0.05          # train PR-AUC minus validation PR-AUC above this is flagged as overfitting
PERMUTATION_REPEATS = 10
TOP_MISTAKES = 10
TIE_MARGIN = 0.02           # a validation PR-AUC lead smaller than this is called a tie (900 rows, see Limits)

DISCLAIMER = (
    "Educational comparison on synthetic data. Not medical advice, not a diagnosis, and not a prediction about "
    "any real person or appointment. This report ships no model: the API still uses noshow-1.0.0."
)
TEST_PILE_NOTE = (
    "The test pile was already used in Week 3 to report the baseline, logistic regression and gradient boosting, "
    "so it is no longer completely unseen. In Week 4 every comparison and every choice is made on the validation "
    "pile only. The test numbers, including the first ones for random forest, are reported afterwards and are "
    "not used to choose anything."
)


# ---------------------------------------------------------------- building blocks (unit-tested)
def cv_folds(train):
    """The 5 stratified folds of the training pile, as (fit positions, held-out positions) inside that pile."""
    return list(models.cv_splitter().split(features.features_of(train), features.target_of(train)))


def cross_validation(fitted, train):
    """Re-fit an unfitted copy of the (tuned) pipeline on each fold of the training pile; score the held-out fold."""
    scores = cross_validate(
        clone(fitted), features.features_of(train), features.target_of(train), cv=cv_folds(train),
        scoring={"roc_auc": "roc_auc", "pr_auc": "average_precision"}, n_jobs=1,
    )
    out = {"rows": len(train)}
    for metric in ("roc_auc", "pr_auc"):
        folds = [float(v) for v in scores[f"test_{metric}"]]
        out[metric] = {"mean": float(np.mean(folds)), "sd": float(np.std(folds)), "folds": folds}
    return out


def importance_table(model, X, y):
    """Permutation importance: how much PR-AUC drops when one input column is shuffled. Most important first."""
    raw = permutation_importance(model, X, y, scoring="average_precision", n_repeats=PERMUTATION_REPEATS,
                                 random_state=models.SEED, n_jobs=1)
    rows = [
        {"feature": str(column), "mean": round(float(mean), 4), "sd": round(float(sd), 4)}
        for column, mean, sd in zip(X.columns, raw.importances_mean, raw.importances_std)
    ]
    return sorted(rows, key=lambda row: row["mean"], reverse=True)


def best_on_validation(validation):
    """The trained model with the highest validation PR-AUC. The baseline is a reference, never a choice."""
    trained = [name for name in validation if name != "baseline"]
    return max(trained, key=lambda name: validation[name]["pr_auc"])


def _proba(model, pile):
    return model.predict_proba(features.features_of(pile))[:, 1]


# ---------------------------------------------------------------- the run
def run(frame):
    return fit_and_evaluate(frame)[0]


def fit_and_evaluate(frame):
    """The whole workbench on the committed dataset. Returns (results, fitted pipelines by name)."""
    _, true_score = gen.simulate(gen.DEFAULT_SEED, gen.DEFAULT_ROWS, gen.DEFAULT_NOISE)
    if len(frame) != len(true_score):
        raise ValueError("The workbench expects the committed dataset (seed 42, 6000 rows, noise 1.0).")
    split = features.split_data(frame)
    piles = {"train": split.train, "validation": split.validation, "test": split.test}
    y = {name: features.target_of(pile).to_numpy() for name, pile in piles.items()}
    ceilings = {name: float(roc_auc_score(y[name], true_score[pile.index])) for name, pile in piles.items()}

    # ---- 1. fit on the training pile (tuning by cross-validation inside it)
    fitted, per_model, rf_search = {}, {}, []
    for name in models.WORKBENCH_CANDIDATES:
        if name == "random_forest":
            fitted[name], tuning, rf_search = models.tune_random_forest(split.train)
        else:
            fitted[name], tuning = models.fit_candidate(name, split.train)
        per_model[name] = {"tuning": tuning, "cv": cross_validation(fitted[name], split.train)}

    # ---- 2. validation: thresholds, metrics, train-vs-validation, leakage alarm, the choice
    p_val = {}
    for name in models.WORKBENCH_CANDIDATES:
        p_val[name] = _proba(fitted[name], split.validation)
        ranking = evaluate.ranking_metrics(y["validation"], p_val[name])
        evaluate.check_leakage(ranking["roc_auc"], ceilings["validation"], "validation", name)
        threshold = evaluate.choose_threshold(y["validation"], p_val[name])
        validation = {**ranking, **evaluate.threshold_metrics(y["validation"], p_val[name], threshold)}
        p_train = _proba(fitted[name], split.train)
        train = {**evaluate.ranking_metrics(y["train"], p_train),
                 "f1": evaluate.threshold_metrics(y["train"], p_train, threshold)["f1"]}
        gap = round(train["pr_auc"], 4) - round(validation["pr_auc"], 4)
        per_model[name].update({
            "train": train, "validation": validation,
            "gap": {"pr_auc": gap, "overfit": bool(gap > OVERFIT_GAP)},
        })
    best = best_on_validation({name: per_model[name]["validation"] for name in models.WORKBENCH_CANDIDATES})
    best_threshold = per_model[best]["validation"]["threshold"]

    importance = {
        name: importance_table(fitted[name], features.features_of(split.validation),
                               features.target_of(split.validation))
        for name in models.WORKBENCH_CANDIDATES if name != "baseline"
    }
    errors = {
        "model": best, "threshold": best_threshold,
        "profile": evaluate.error_profile(split.validation, p_val[best], best_threshold),
        **evaluate.confident_mistakes(split.validation, p_val[best], best_threshold, top=TOP_MISTAKES),
    }

    # ---- 3. the test pile, for the record only: every threshold and the choice are already fixed
    test = {}
    for name in models.WORKBENCH_CANDIDATES:
        p_test = _proba(fitted[name], split.test)
        ranking = evaluate.ranking_metrics(y["test"], p_test)
        evaluate.check_leakage(ranking["roc_auc"], ceilings["test"], "test", name)
        test[name] = {**ranking, **evaluate.threshold_metrics(
            y["test"], p_test, per_model[name]["validation"]["threshold"])}

    results = _rounded({
        "version": VERSION,
        "disclaimer": DISCLAIMER,
        "test_pile_note": TEST_PILE_NOTE,
        "settings": {
            "split_seed": features.SPLIT_SEED, "model_seed": models.SEED, "cv_folds": models.CV_FOLDS,
            "rf_search_tries": models.RF_SEARCH_TRIES, "permutation_repeats": PERMUTATION_REPEATS,
            "overfit_gap": OVERFIT_GAP, "leakage_margin": evaluate.LEAKAGE_MARGIN,
            "scikit_learn": sklearn.__version__, "shipped_model": "noshow-1.0.0",
        },
        "pile_sizes": {name: {"rows": len(pile), "no_shows": int(y[name].sum())} for name, pile in piles.items()},
        "ceilings": ceilings,
        "models": per_model,
        "rf_search": rf_search,
        "best_on_validation": best,
        "importance": importance,
        "errors": errors,
        "test": test,
    })
    return results, fitted


# ---------------------------------------------------------------- the report
NAMES = {"baseline": "Baseline", "logistic_regression": "Logistic regression", "random_forest": "Random forest",
         "gradient_boosting": "Gradient boosting"}


# ---------------------------------------------------------------- honest wording, computed from the numbers
def _trained(models_):
    return [name for name in models.WORKBENCH_CANDIDATES if name != "baseline" and name in models_]


def tie_note(models_):
    ranked = sorted(_trained(models_), key=lambda n: models_[n]["validation"]["pr_auc"], reverse=True)
    first, second = ranked[0], ranked[1]
    lead = models_[first]["validation"]["pr_auc"] - models_[second]["validation"]["pr_auc"]
    if lead < TIE_MARGIN:
        return (f"{NAMES[first]} and {NAMES[second]} are practically tied: their validation PR-AUC differs by "
                f"{lead:.3f}, well within what luck can move on 900 rows. \"Best\" here is only a label for the "
                "mistake inspection below, not a real win.")
    return f"{NAMES[first]} leads {NAMES[second]} by {lead:.3f} validation PR-AUC."


def harder_pile_note(models_):
    names = _trained(models_)
    if all(models_[n]["validation"]["pr_auc"] < models_[n]["cv"]["pr_auc"]["mean"] for n in names):
        return ("Part of every gap comes from the validation pile itself: each model's validation PR-AUC is below "
                "its cross-validated mean, so this pile is harder than an average fold.")
    return ""


def negative_importance_note(importance):
    found = {}
    for name, table in importance.items():
        for row in table:
            if row["mean"] < 0 and row["mean"] < -2 * row["sd"]:
                found.setdefault(row["feature"], []).append(f"{NAMES[name]} {row['mean']:+.4f} ± {row['sd']:.4f}")
    if not found:
        return ""
    details = "; ".join(f"`{feature}` ({', '.join(parts)})" for feature, parts in found.items())
    return (f"Shuffling these inputs *improved* PR-AUC by more than two standard deviations: {details}. What those "
            "models learned about the input on the training pile does not carry over to the validation pile, a "
            "small sign of overfitting on it. Week 4 reports this and does not fix it.")


def ranking_on_test_note(results):
    test, chosen = results["test"], results["best_on_validation"]
    top = max(_trained(test), key=lambda n: test[n]["pr_auc"])
    if top == chosen:
        return f"On the test pile {NAMES[top]} also has the highest PR-AUC. This is reported, not used to choose."
    return (f"On the test pile {NAMES[top]} has the highest PR-AUC ({test[top]['pr_auc']:.3f}), while "
            f"{NAMES[chosen]}, best on validation, has {test[chosen]['pr_auc']:.3f}. The order changes from one "
            "900-row pile to the next, which shows how small these differences are. The test numbers are not used "
            "to choose anything.")


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    return "\n".join(lines + ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows])


def _f3(value):
    return "-" if value is None else f"{value:.3f}"


def _pct(value):
    return "-" if value is None else f"{100 * value:.1f}%"


def _params(params):
    return ", ".join(f"{key}={value}" for key, value in sorted(params.items())) or "(none)"


def _mistake_rows(records):
    return [
        [r["appointment_id"], _f3(r["p"]), r["lead_time_days"], r["weekday"], r["hour"], r["visit_type"],
         r["booking_channel"], r["reminder_sent"] or "(blank)",
         "(blank)" if r["prior_visits"] is None else f"{r['prior_no_shows']}/{r['prior_visits']}"]
        for r in records
    ]


def render(results):
    m, names = results["models"], models.WORKBENCH_CANDIDATES
    best = results["best_on_validation"]
    s = results["settings"]

    validation_rows = [
        [NAMES[n], _f3(m[n]["validation"]["roc_auc"]), _f3(m[n]["validation"]["pr_auc"]),
         f"{m[n]['validation']['threshold']:.2f}", _f3(m[n]["validation"]["precision"]),
         _f3(m[n]["validation"]["recall"]), _f3(m[n]["validation"]["f1"]),
         m[n]["validation"]["tp"], m[n]["validation"]["fp"], m[n]["validation"]["fn"], m[n]["validation"]["tn"]]
        for n in names
    ]
    gap_rows = [
        [NAMES[n], _f3(m[n]["train"]["roc_auc"]), _f3(m[n]["validation"]["roc_auc"]),
         _f3(m[n]["train"]["pr_auc"]), _f3(m[n]["validation"]["pr_auc"]), f"{m[n]['gap']['pr_auc']:+.3f}",
         _f3(m[n]["train"]["f1"]), _f3(m[n]["validation"]["f1"]), "yes" if m[n]["gap"]["overfit"] else "no"]
        for n in names
    ]
    cv_rows = [
        [NAMES[n], f"{m[n]['cv']['roc_auc']['mean']:.3f} ± {m[n]['cv']['roc_auc']['sd']:.3f}",
         f"{m[n]['cv']['pr_auc']['mean']:.3f} ± {m[n]['cv']['pr_auc']['sd']:.3f}",
         _params(m[n]["tuning"]["best_params"])]
        for n in names
    ]
    search_rows = [
        [i + 1, _params(t["params"]), f"{t['cv_pr_auc_mean']:.3f} ± {t['cv_pr_auc_sd']:.3f}",
         "best" if t["params"] == m["random_forest"]["tuning"]["best_params"] else ""]
        for i, t in enumerate(sorted(results["rf_search"], key=lambda t: -t["cv_pr_auc_mean"]))
    ]
    importance_sections = "\n\n".join(
        f"**{NAMES[n]}**\n\n" + _table(
            ["Input", "Drop in PR-AUC when shuffled (mean ± sd)"],
            [[row["feature"], f"{row['mean']:+.4f} ± {row['sd']:.4f}"] for row in results["importance"][n]])
        for n in results["importance"]
    )
    e = results["errors"]
    profile_rows = [
        [box["box"], box["rows"], _f3(box["mean_predicted"]), _pct(box["no_reminder"]), _f3(box["mean_lead_time"]),
         _pct(box["any_prior_no_show"]), _pct(box["phone_booking"])]
        for box in e["profile"]
    ]
    mistake_headers = ["Row", "Predicted", "Lead days", "Day", "Hour", "Visit", "Channel", "Reminder",
                       "Prior no-shows/visits"]
    t = results["test"]
    test_rows = [
        [NAMES[n], _f3(t[n]["roc_auc"]), _f3(t[n]["pr_auc"]), f"{t[n]['threshold']:.2f}", _f3(t[n]["precision"]),
         _f3(t[n]["recall"]), _f3(t[n]["f1"]), t[n]["tp"], t[n]["fp"], t[n]["fn"], t[n]["tn"]]
        for n in names
    ]
    overfit = [NAMES[n] for n in names if m[n]["gap"]["overfit"]]
    overfit_text = (", ".join(overfit) + f" show a train-minus-validation PR-AUC gap above {s['overfit_gap']}."
                    if overfit else f"No model shows a train-minus-validation PR-AUC gap above {s['overfit_gap']}.")
    widest = max(_trained(m), key=lambda n: m[n]["gap"]["pr_auc"])
    widest_text = (f"The gap that stands out is {NAMES[widest]}'s ({m[widest]['gap']['pr_auc']:+.3f}, training "
                   f"PR-AUC {m[widest]['train']['pr_auc']:.3f}): it fits the training rows far more closely than "
                   "new rows.")
    ranking_headers = ["Model", "ROC-AUC", "PR-AUC", "Threshold", "Precision", "Recall", "F1", "TP", "FP", "FN", "TN"]
    sizes = results["pile_sizes"]

    return f"""# Week 4 supervised workbench ({results['version']})

> **{results['disclaimer']}**

Generated by `python -m ml.workbench` from the committed dataset; a test checks this file matches a fresh run.
Machine-readable copy: [`backend/ml/reports/workbench.json`](../../backend/ml/reports/workbench.json).

## The test pile was reused, so choices use validation only

{results['test_pile_note']}

## Setup

* Same split as Week 3: {sizes['train']['rows']} training, {sizes['validation']['rows']} validation and
  {sizes['test']['rows']} test rows (split seed {s['split_seed']}), stratified on no-show.
* Every model is one scikit-learn Pipeline: the Week 3 preprocessing (training medians, blank indicators, scaling,
  one-hot) and then the model. It is fitted on the training pile only; cross-validation refits the preprocessing
  inside every fold.
* Model seed {s['model_seed']}, {s['cv_folds']}-fold stratified cross-validation, one CPU core, scikit-learn
  {s['scikit_learn']} (pinned in `requirements.txt`).
* Logistic regression and gradient boosting keep their Week 3 grid search. **Random forest is the tuned model of
  Week 4**: RandomizedSearchCV tried {s['rf_search_tries']} seeded settings, scored by cross-validated PR-AUC.
* Each model's threshold is the one with the best F1 on the validation pile (ties go to the higher threshold).

## 1. Validation comparison (the only basis for any choice)

{_table(ranking_headers, validation_rows)}

Best on validation PR-AUC: **{NAMES[best]}**. {tie_note(m)} It does not replace noshow-1.0.0. TP = caught no-shows, FP = false alarms, FN = missed no-shows, TN = correctly cleared attenders.

## 2. Training versus validation

{_table(["Model", "Train ROC-AUC", "Val ROC-AUC", "Train PR-AUC", "Val PR-AUC", "PR-AUC gap", "Train F1",
         "Val F1", f"Gap > {s['overfit_gap']}?"], gap_rows)}

{overfit_text} {widest_text} {harder_pile_note(m)} F1 on both piles uses the threshold chosen on validation.

## 3. Stratified cross-validation (training pile only)

{_table(["Model", "CV ROC-AUC (mean ± sd)", "CV PR-AUC (mean ± sd)", "Settings used"], cv_rows)}

The folds are the ones tuning used, so for the tuned models these numbers lean slightly optimistic: the
settings were picked because they scored well on exactly these folds. The ± shows how much a score moves from one
fold of 840 rows to the next.

## 4. Random forest tuning (RandomizedSearchCV, {s['rf_search_tries']} settings)

{_table(["#", "Settings", "CV PR-AUC (mean ± sd)", ""], search_rows)}

## 5. Permutation importance (validation pile, {s['permutation_repeats']} shuffles per input)

How much PR-AUC drops when one input column is shuffled, breaking its link to the outcome. A value near zero means
the model barely relies on that input (small negative values are noise; read them as zero); it does not mean the input is unrelated to no-shows (two inputs that carry
the same information share the credit). The data follows a rule we wrote, so these numbers describe that rule.

{importance_sections}

{negative_importance_note(results['importance'])}

## 6. False positives and false negatives ({NAMES[best]}, validation, threshold {e['threshold']:.2f})

{_table(["Box", "Rows", "Avg predicted", "No reminder", "Avg lead days", "Any prior no-show", "Booked by phone"],
        profile_rows)}

**Most confident false alarms** (predicted likely to miss, but attended):

{_table(mistake_headers, _mistake_rows(e['false_alarms']))}

**Most confident misses** (predicted likely to attend, but missed):

{_table(mistake_headers, _mistake_rows(e['misses']))}

The data is noisy on purpose (a seeded coin flip decides each outcome), so some confident mistakes are the coin, not
the model.

## 7. Test pile (reported afterwards, not used to choose)

{_table(ranking_headers, test_rows)}

Thresholds are the ones frozen on validation. {ranking_on_test_note(results)}

## Limits

* Synthetic data generated from a rule we wrote: the scores show the method working and say nothing about real
  clinics or real people.
* One split and one seed; validation and test have 900 rows each, so differences of a few hundredths between models
  can be luck. No new bootstrap intervals were computed in Week 4 (cut for time); see the Week 3 model report for
  the intervals of the Week 3 models.
* This workbench ships no model. The API keeps serving noshow-1.0.0, unchanged and checksum-verified.
"""


def main():
    results = run(gen.load_csv())
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_bytes((json.dumps(results, indent=2) + "\n").encode("utf-8"))
    REPORT_PATH.write_bytes(render(results).encode("utf-8"))
    print(f"Wrote {RESULTS_PATH} and {REPORT_PATH} (best on validation: {results['best_on_validation']})")


if __name__ == "__main__":
    main()
