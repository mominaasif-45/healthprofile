"""
Phase 3 experiment: train the three candidates, compare them on the validation pile, choose a model and
its threshold by the rules in evaluate.py, and only then open the test pile, once.

Writes docs/ml/model-report.md and backend/ml/reports/metrics.json. Run from backend/:

    python -m ml.experiment
"""
import json
from pathlib import Path

from sklearn.metrics import roc_auc_score

from ml import evaluate, features, models
from ml.data import generate as gen

REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "ml" / "model-report.md"
METRICS_PATH = Path(__file__).resolve().parent / "reports" / "metrics.json"
RULE_REFERENCE = {"age_band": "45-54", "booking_channel": "phone", "distance_band": "under_5km"}  # rule effect 0


def _proba(model, pile):
    return model.predict_proba(features.features_of(pile))[:, 1]


def _rounded(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rounded(v) for v in value]
    return value


def _learned_vs_rule(model):
    """Logistic regression's learned effect of each group value (vs the rule's zero value) next to the rule's number."""
    names = list(model.named_steps["preprocess"].get_feature_names_out())
    coef = dict(zip(names, model.named_steps["model"].coef_[0]))
    rows = []
    for column, reference in RULE_REFERENCE.items():
        for value in gen.CATEGORIES[column]:
            rows.append({
                "column": column, "value": value, "reference": reference,
                "rule": float(gen.EFFECTS[column].get(value, 0.0)),
                "learned": float(coef[f"cat__{column}_{value}"] - coef[f"cat__{column}_{reference}"]),
            })
    return rows


def run(frame):
    """The whole experiment on `frame` (the committed dataset). Raises LeakageAlarm on a too-good score."""
    _, true_score = gen.simulate(gen.DEFAULT_SEED, gen.DEFAULT_ROWS, gen.DEFAULT_NOISE)
    if len(frame) != len(true_score):
        raise ValueError("The experiment expects the committed dataset (seed 42, 6000 rows, noise 1.0).")
    split = features.split_data(frame)
    piles = {"train": split.train, "validation": split.validation, "test": split.test}
    y = {name: features.target_of(pile).to_numpy() for name, pile in piles.items()}
    # The rule's own score on each pile: the best any honest model can do there, give or take luck.
    ceilings = {name: float(roc_auc_score(y[name], true_score[pile.index])) for name, pile in piles.items()}

    # ---- 1. fit on train, score on validation, check for leakage, choose each model's threshold
    fitted, tuning, train_scores, validation, p_val = {}, {}, {}, {}, {}
    for name in models.CANDIDATES:
        fitted[name], tuning[name] = models.fit_candidate(name, split.train)
        p_train = _proba(fitted[name], split.train)
        train_scores[name] = {k: v for k, v in evaluate.ranking_metrics(y["train"], p_train).items() if k != "brier"}
        p_val[name] = _proba(fitted[name], split.validation)
        ranking = evaluate.ranking_metrics(y["validation"], p_val[name])
        evaluate.check_leakage(ranking["roc_auc"], ceilings["validation"], "validation", name)
        threshold = evaluate.choose_threshold(y["validation"], p_val[name])
        validation[name] = {**ranking, **evaluate.threshold_metrics(y["validation"], p_val[name], threshold)}

    # ---- 2. compare and choose, on validation only
    yv = y["validation"]
    comparisons = {
        "logistic_regression_vs_baseline": evaluate.paired_difference(yv, p_val["logistic_regression"], p_val["baseline"]),
        "gradient_boosting_vs_baseline": evaluate.paired_difference(yv, p_val["gradient_boosting"], p_val["baseline"]),
        "gradient_boosting_vs_logistic_regression": evaluate.paired_difference(
            yv, p_val["gradient_boosting"], p_val["logistic_regression"]),
    }
    decisive = comparisons["gradient_boosting_vs_logistic_regression"]
    chosen = evaluate.select_model((decisive["low"], decisive["high"]))
    threshold = validation[chosen]["threshold"]

    # ---- 3. the test pile: opened once, after the choice and every threshold are fixed
    test, p_test = {}, {}
    for name in models.CANDIDATES:
        p_test[name] = _proba(fitted[name], split.test)
        ranking = evaluate.ranking_metrics(y["test"], p_test[name])
        evaluate.check_leakage(ranking["roc_auc"], ceilings["test"], "test", name)
        test[name] = {**ranking, **evaluate.threshold_metrics(y["test"], p_test[name], validation[name]["threshold"])}

    return _rounded({
        "settings": {
            "split_seed": features.SPLIT_SEED, "model_seed": models.SEED, "cv_folds": models.CV_FOLDS,
            "bootstrap_rounds": evaluate.BOOTSTRAP_ROUNDS, "leakage_margin": evaluate.LEAKAGE_MARGIN,
            "max_plausible_auc": evaluate.MAX_PLAUSIBLE_AUC, "small_rows": evaluate.SMALL_ROWS,
            "small_no_shows": evaluate.SMALL_NO_SHOWS,
        },
        "pile_sizes": {name: {"rows": len(pile), "no_shows": int(y[name].sum())} for name, pile in piles.items()},
        "ceilings": ceilings,
        "tuning": tuning,
        "train": train_scores,
        "validation": validation,
        "comparisons": comparisons,
        "chosen": chosen,
        "threshold_table": evaluate.threshold_table(yv, p_val[chosen]),
        "test": test,
        "groups": {
            "validation": evaluate.group_table(split.validation, p_val[chosen], threshold),
            "test": evaluate.group_table(split.test, p_test[chosen], threshold),
        },
        "calibration": {
            "validation": evaluate.calibration_table(yv, p_val[chosen]),
            "test": evaluate.calibration_table(y["test"], p_test[chosen]),
        },
        "errors": {
            "profile": evaluate.error_profile(split.validation, p_val[chosen], threshold),
            **evaluate.confident_mistakes(split.validation, p_val[chosen], threshold),
        },
        "learned_vs_rule": _learned_vs_rule(fitted["logistic_regression"]),
    })


# ---------------------------------------------------------------- the report
NAMES = {"baseline": "Baseline", "logistic_regression": "Logistic regression", "gradient_boosting": "Gradient boosting"}
GROUP_NOTE = "too small to judge"


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows])


def _f3(value):
    return "n/a" if value is None else f"{value:.3f}"


def _pct(value):
    return "n/a" if value is None else f"{value:.1%}"


def _signed(value):
    return f"{value:+.3f}"


def _interval(metric):
    if metric["value"] is None:
        return "n/a"
    return f"{_pct(metric['value'])} ({_pct(metric['low'])} to {_pct(metric['high'])})"


def _metric_rows(scores):
    return [
        [NAMES[name], _f3(s["roc_auc"]), _f3(s["pr_auc"]), _f3(s["brier"]), f"{s['threshold']:.2f}",
         _pct(s["precision"]), _pct(s["recall"]), _f3(s["f1"]), _pct(s["balanced_accuracy"]), _pct(s["accuracy"])]
        for name, s in scores.items()
    ]


METRIC_HEADERS = ["Model", "ROC-AUC", "PR-AUC", "Brier", "Threshold", "Precision", "Recall", "F1",
                  "Balanced acc.", "Accuracy"]


def _group_rows(rows):
    return [
        [f"{r['column']} = {r['value']}", r["rows"], r["no_shows"], _pct(r["actual_rate"]), _pct(r["mean_predicted"]),
         _interval(r["recall"]), _interval(r["false_alarm_rate"]), _interval(r["precision"]),
         GROUP_NOTE if r["small"] else ""]
        for r in rows
    ]


GROUP_HEADERS = ["Group", "Rows", "No-shows", "Actual rate", "Avg predicted", "Recall (95% interval)",
                 "False-alarm rate (95% interval)", "Precision (95% interval)", "Note"]


def _group_findings(rows):
    """For each group column: the highest and lowest false-alarm rate among groups big enough to judge."""
    lines = []
    for column in evaluate.GROUP_COLUMNS:
        judged = [r for r in rows if r["column"] == column and not r["small"] and r["false_alarm_rate"]["value"] is not None]
        if len(judged) < 2:
            continue
        high = max(judged, key=lambda r: r["false_alarm_rate"]["value"])
        low = min(judged, key=lambda r: r["false_alarm_rate"]["value"])
        separate = high["false_alarm_rate"]["low"] > low["false_alarm_rate"]["high"]
        verdict = ("the intervals do **not** overlap, so this is a clear difference" if separate
                   else "the intervals overlap, so this is **not** clear evidence of a difference")
        lines.append(
            f"* **{column}**: false alarms range from {_pct(low['false_alarm_rate']['value'])} (`{low['value']}`) "
            f"to {_pct(high['false_alarm_rate']['value'])} (`{high['value']}`) among groups big enough to judge; "
            f"{verdict}."
        )
    return "\n".join(lines)


def _mistake_rows(records):
    return [
        [r["appointment_id"], f"{r['p']:.2f}", r["lead_time_days"], r["weekday"], r["hour"], r["visit_type"],
         r["booking_channel"], r["reminder_sent"] or "(blank)",
         "(blank)" if r["prior_visits"] is None else f"{r['prior_no_shows']} of {r['prior_visits']}",
         r["distance_band"] or "(blank)", r["age_band"] or "(blank)"]
        for r in records
    ]


MISTAKE_HEADERS = ["Row", "Predicted", "Lead days", "Day", "Hour", "Visit", "Channel", "Reminder",
                   "Earlier no-shows", "Distance", "Age"]


def render(results):
    chosen = results["chosen"]
    name = NAMES[chosen]
    val, test, base = results["validation"][chosen], results["test"][chosen], results["test"]["baseline"]
    threshold = val["threshold"]
    ceilings, margin = results["ceilings"], results["settings"]["leakage_margin"]
    decisive = results["comparisons"]["gradient_boosting_vs_logistic_regression"]
    boosting_clear = decisive["low"] > 0
    profile = {row["box"]: row for row in results["errors"]["profile"]}
    tp, fn = profile["caught no-shows (TP)"], profile["missed no-shows (FN)"]
    fp, tn = profile["false alarms (FP)"], profile["correctly cleared (TN)"]
    calibration_gap = max(abs(b["mean_predicted"] - b["actual_rate"]) for b in results["calibration"]["test"])

    comparison_rows = [
        [label, _signed(c["diff"]), f"{_signed(c['low'])} to {_signed(c['high'])}",
         "yes" if c["low"] > 0 else "no (interval includes zero or is below it)"]
        for label, c in (
            ("Logistic regression vs baseline", results["comparisons"]["logistic_regression_vs_baseline"]),
            ("Gradient boosting vs baseline", results["comparisons"]["gradient_boosting_vs_baseline"]),
            ("Gradient boosting vs logistic regression", decisive),
        )
    ]
    leakage_rows = [
        [NAMES[m], *(f"{results[p][m]['roc_auc']:.3f} (ceiling {ceilings[p]:.3f}, limit "
                     f"{min(ceilings[p] + margin, results['settings']['max_plausible_auc']):.3f})"
                     for p in ("validation", "test"))]
        for m in models.CANDIDATES
    ]
    overfit_rows = [
        [NAMES[m], _f3(results["train"][m]["roc_auc"]), _f3(results["validation"][m]["roc_auc"]),
         _signed(results["train"][m]["roc_auc"] - results["validation"][m]["roc_auc"]),
         _f3(results["train"][m]["pr_auc"]), _f3(results["validation"][m]["pr_auc"])]
        for m in models.CANDIDATES
    ]
    tuning_rows = [
        [NAMES[m], ", ".join(f"`{k}={v}`" for k, v in t["best_params"].items()) or "none (nothing to tune)",
         _f3(t["cv_pr_auc"])]
        for m, t in results["tuning"].items()
    ]
    threshold_rows = [
        [f"{t['threshold']:.2f}" + (" (chosen)" if t["threshold"] == threshold else ""), _pct(t["recall"]),
         _pct(t["precision"]), _f3(t["f1"]), t["tp"] + t["fp"], t["fp"]]
        for t in results["threshold_table"]
    ]
    calibration_rows = lambda bands: [  # noqa: E731
        [b["band"], b["rows"], f"{b['min_p']:.2f} to {b['max_p']:.2f}", _pct(b["mean_predicted"]), _pct(b["actual_rate"])]
        for b in bands
    ]
    profile_rows = [
        [r["box"], r["rows"], _pct(r["mean_predicted"]), _pct(r["no_reminder"]), f"{r['mean_lead_time']:.1f}",
         _pct(r["any_prior_no_show"]), _pct(r["phone_booking"])]
        for r in results["errors"]["profile"]
    ]
    learned_rows = [
        [f"{r['column']} = {r['value']}", r["reference"], _signed(r["rule"]), _signed(r["learned"])]
        for r in results["learned_vs_rule"] if r["value"] != r["reference"]
    ]
    sizes = results["pile_sizes"]
    gaps = {m: results["train"][m]["roc_auc"] - results["validation"][m]["roc_auc"] for m in models.CANDIDATES}
    false_alarms, misses = results["errors"]["false_alarms"], results["errors"]["misses"]
    fa_long = sum(r["lead_time_days"] >= 30 for r in false_alarms)
    fa_no_reminder = sum(r["reminder_sent"] == "no" for r in false_alarms)
    miss_reminder = sum(r["reminder_sent"] == "yes" for r in misses)
    miss_clean = sum(r["prior_no_shows"] == 0 for r in misses)

    if boosting_clear:
        complexity = (f"Gradient boosting was **clearly better** than logistic regression on validation PR-AUC "
                      f"({_signed(decisive['diff'])}, interval {_signed(decisive['low'])} to {_signed(decisive['high'])}), "
                      "so it earned its extra complexity and was chosen.")
    else:
        complexity = (f"Gradient boosting was **not clearly better** than logistic regression: its validation PR-AUC "
                      f"advantage was {_signed(decisive['diff'])}, but the 95% interval runs from {_signed(decisive['low'])} "
                      f"to {_signed(decisive['high'])} and includes zero. By the rule fixed in advance, the simpler "
                      "**logistic regression** was chosen. This is a finding, not a failure: the more complex model did "
                      "not earn its complexity on this data. That is expected here, because our generating rule is itself "
                      "a sum of weights, which is exactly the shape logistic regression assumes.")

    return f"""# Model report: synthetic appointment no-show likelihood

> **Educational demo on synthetic data.** Not medical advice, not a diagnosis, not a real clinic. Every number
> below shows how well a method recovers a pattern **we wrote** into invented data (see the
> [data card](data-card.md)); it says nothing about real appointments or real people.
>
> Generated by `python -m ml.experiment`; do not edit by hand (a test checks this file matches the script).
> The same numbers are in [`backend/ml/reports/metrics.json`](../../backend/ml/reports/metrics.json).

## Summary

* **Chosen model: {name}**, with the decision threshold **{threshold:.2f}** (best F1 on validation, then frozen).
* **Final exam (test pile, {sizes['test']['rows']} rows, used once):** ROC-AUC **{test['roc_auc']:.3f}**,
  PR-AUC **{test['pr_auc']:.3f}** (baseline {base['pr_auc']:.3f}). At the threshold it caught **{_pct(test['recall'])}**
  of no-shows ({test['tp']} of {test['tp'] + test['fn']}), and **{_pct(test['precision'])}** of its flags were real
  no-shows ({test['tp']} of {test['tp'] + test['fp']}).
* {complexity}
* **No leakage alarm.** Every model stayed below the ceiling of its pile plus the {margin} margin (section 5).
* **Modest, as expected.** The best any model could do on the test pile is ROC-AUC {ceilings['test']:.3f} (our own
  rule). A large share of no-shows here are unpredictable by design (section 10).

## 1. How the models were compared (rules fixed before seeing results)

* **Split** (phase 2): {sizes['train']['rows']:,} training / {sizes['validation']['rows']} validation / {sizes['test']['rows']}
  test rows, each about 20.8% no-shows.
* **Training:** each model is one Pipeline (preprocessing + model) fitted on the training pile. Settings were tuned by
  {results['settings']['cv_folds']}-fold cross-validation **inside the training pile**, scored by PR-AUC.
* **Comparing and choosing:** on the validation pile only. Gradient boosting is chosen only if its PR-AUC advantage over
  logistic regression has a paired 95% bootstrap interval ({results['settings']['bootstrap_rounds']:,} resamples, seed 42)
  entirely above zero. Otherwise the simpler logistic regression wins.
* **Threshold:** for each model, the threshold from 0.05 to 0.95 with the best F1 on validation (ties go to the higher
  one), then frozen.
* **Test pile:** opened once, after the choice and every threshold were fixed.
* **No class weights:** they would inflate every probability. The API returns a probability, so it should mean what it
  says; the imbalance is handled by the threshold instead.

**Metrics in plain words.** *ROC-AUC*: the chance a random no-show gets a higher score than a random attender (0.5 =
guessing). *PR-AUC*: how precise the model stays as it finds more no-shows; the fairer score when only about 1 in 5 is a
no-show (the baseline scores about 0.21). *Brier*: average squared gap between the predicted chance and what happened
(lower is better). *Recall*: share of real no-shows flagged. *Precision*: share of flags that were real no-shows.
*F1*: one number balancing the two. *Balanced accuracy*: the average of the hit rate on no-shows and on attenders.
*Accuracy* is shown only for completeness: "everyone attends" would score 79.2%.

## 2. Tuning (cross-validation on the training pile)

{_table(["Model", "Best settings", "Cross-validated PR-AUC"], tuning_rows)}

## 3. Validation results

{_table(METRIC_HEADERS, _metric_rows(results["validation"]))}

The baseline gives everyone the same chance, so its "best F1" threshold flags **everyone**: it catches every no-show
with {_pct(results['validation']['baseline']['precision'])} precision. That sets a low bar for F1
({results['validation']['baseline']['f1']:.3f}); the real models beat it, but not by much at any single threshold. Their
advantage is clearer in PR-AUC, which looks at every threshold at once.

**Training vs validation (memorising, not leakage):**

{_table(["Model", "Train ROC-AUC", "Validation ROC-AUC", "Gap", "Train PR-AUC", "Validation PR-AUC"], overfit_rows)}

A model that scores much better on rows it trained on than on new rows has memorised some noise. The ROC-AUC gap is
{_signed(gaps['gradient_boosting'])} for gradient boosting and {_signed(gaps['logistic_regression'])} for logistic
regression.

## 4. Is the more complex model better?

Paired bootstrap on the validation pile: both models are scored on the same resampled rows {results['settings']['bootstrap_rounds']:,}
times, and the middle 95% of the differences in PR-AUC is the interval.

{_table(["Comparison (PR-AUC)", "Difference", "95% interval", "Clearly better?"], comparison_rows)}

Both models are clearly better than the baseline (their intervals are entirely above zero), so the "improved model"
requirement is met. {complexity}

## 5. Leakage alarm

**The ceiling.** We wrote the rule, so we know each row's true risk score. Ranking the rows by that score gives the
best ROC-AUC anyone could honestly get, because the noise and the final coin flip cannot be predicted from the
columns. On the whole file it is 0.657; on each pile it is: train **{ceilings['train']:.3f}**, validation
**{ceilings['validation']:.3f}**, test **{ceilings['test']:.3f}**.

**The margin ({margin}).** The ceiling is measured on the same finite pile as the model, so luck matters: on 900 rows,
an honest model can land a little above the rule's score just because of which rows happened to be in the pile. The
alarm therefore goes off only if a model beats its pile's ceiling by **more than {margin}**, or if any ROC-AUC is above
**{results['settings']['max_plausible_auc']}**. Either one stops the experiment with a `LeakageAlarm` before any result
is written. A test plants a copy of the answer as an input and checks that the alarm goes off.

{_table(["Model", "Validation ROC-AUC", "Test ROC-AUC"], leakage_rows)}

## 6. The decision threshold

The model gives a probability; the threshold is the line above which we say "likely to miss". At 0.5 almost nobody
would be flagged, because most probabilities here are between 0.1 and 0.4. Other thresholds for the chosen model on
the validation pile:

{_table(["Threshold", "Recall", "Precision", "F1", "Flagged", "False alarms"], threshold_rows)}

Lower thresholds catch more no-shows at the price of more false alarms. In a real clinic the cost of each kind of
mistake would decide; for this demo, the best F1 is a neutral choice.

## 7. Final exam: the test pile (used once)

{_table(METRIC_HEADERS, _metric_rows(results["test"]))}

Each model uses its own threshold from validation. For the chosen model, ROC-AUC moved from {val['roc_auc']:.3f}
(validation) to {test['roc_auc']:.3f} (test) and PR-AUC from {val['pr_auc']:.3f} to {test['pr_auc']:.3f}: differences of
this size are ordinary luck between two 900-row piles, which is what we hope to see when nothing about the test pile
influenced the choices.

## 8. Results by group

These are the groups from the data card: age band, booking channel and distance band (blanks included), for the
chosen model at its frozen threshold. Each rate comes with a **95% bootstrap interval**: the group's rows are resampled
{results['settings']['bootstrap_rounds']:,} times and the middle 95% of the results is shown. Groups with fewer than
{results['settings']['small_rows']} rows or fewer than {results['settings']['small_no_shows']} no-shows are marked
**{GROUP_NOTE}**: their intervals are very wide, and no conclusion should be drawn from them.

**Remember:** every difference between groups in this data was **written into the rule by us, on purpose and
arbitrarily** (for example +0.45 for age 18-24, +0.60 for over 30 km). When the model gives a group higher
probabilities, it is reproducing that invented difference. This is how bias in data becomes bias in a model; it is not
a fact about any real group of people.

**Test pile** (the final numbers):

{_table(GROUP_HEADERS, _group_rows(results["groups"]["test"]))}

What the test pile shows:

{_group_findings(results["groups"]["test"])}

* Where false alarms are higher, the model is flagging people **because of their group**, as the rule told it to.
  A real system would need to decide whether that is acceptable before using any such input.

**Validation pile** (a second look; same model and threshold):

{_table(GROUP_HEADERS, _group_rows(results["groups"]["validation"]))}

## 9. Are the probabilities honest? (calibration)

The test rows are sorted into 10 equal bands by predicted probability; in each band the average predicted chance is
compared with how many really missed. The largest gap in any band is {_pct(calibration_gap)}, with about 90 rows per
band, so gaps of a few points are expected from luck alone.

{_table(["Band", "Rows", "Predicted range", "Avg predicted", "Actual no-show rate"], calibration_rows(results["calibration"]["test"]))}

## 10. Error analysis (validation pile)

How the four kinds of outcome differ on a few telling inputs:

{_table(["Outcome", "Rows", "Avg predicted", "No reminder", "Avg lead days", "Any earlier no-show", "Phone booking"], profile_rows)}

* **Missed no-shows look like people who attend.** Only {_pct(fn['no_reminder'])} of missed no-shows had no reminder
  (vs {_pct(tp['no_reminder'])} of caught ones), their average lead time was {fn['mean_lead_time']:.1f} days (vs
  {tp['mean_lead_time']:.1f}), and {_pct(fn['any_prior_no_show'])} had an earlier no-show (vs
  {_pct(tp['any_prior_no_show'])}). On these inputs they are close to the correctly cleared rows ({_pct(tn['no_reminder'])},
  {tn['mean_lead_time']:.1f} days, {_pct(tn['any_prior_no_show'])}). Little in the columns tells them apart: in this data
  they missed mostly because of the noise and the coin flip, which no model can see.
* **False alarms look like real no-shows.** They share the warning signs ({_pct(fp['no_reminder'])} no reminder,
  {fp['mean_lead_time']:.1f} lead days, {_pct(fp['any_prior_no_show'])} with an earlier no-show) but the person attended.
  A higher-risk appointment is still more likely to be attended than missed.
* **Conclusion:** most mistakes are the unpredictable part we built in, not a fixable model fault. No honest model can
  get meaningfully past the ceiling of {ceilings['validation']:.3f} on this pile.

**Most confident false alarms** (attended, but given the highest probabilities):

{_table(MISTAKE_HEADERS, _mistake_rows(results["errors"]["false_alarms"]))}

**Most confident misses** (missed, but given the lowest probabilities):

{_table(MISTAKE_HEADERS, _mistake_rows(results["errors"]["misses"]))}

Of the confident false alarms, {fa_long} of {len(false_alarms)} waited 30 days or more and {fa_no_reminder} had no
reminder. Of the confident misses, {miss_reminder} of {len(misses)} had a reminder and {miss_clean} had no earlier
no-show: on paper they looked like safe appointments. All rows are fictional.

## 11. What logistic regression learned vs the rule we wrote

Each number is the effect on the risk score (log-odds) compared with the value the rule gives 0:

{_table(["Group value", "Compared with", "Rule (written)", "Learned"], learned_rows)}

The model recovers the direction of most of the planted differences. The learned numbers are smaller and wobblier:
the noise blurs them, regularisation (`C={results['tuning']['logistic_regression']['best_params'].get('C', 'n/a')}`)
shrinks them towards zero, and 4,200 rows are not enough to pin down small effects.

## 12. Limitations

* **Synthetic data follows rules we wrote.** The models rediscover those rules; the scores measure the method, not
  real-world usefulness. Real no-show data has more causes, messier records and changes over time.
* **Small groups** (marked above) cannot be judged; their intervals are too wide.
* **One split, one seed.** The validation and test piles have 900 rows each; the intervals show how much the numbers
  could move with different rows.
* **The threshold** maximises F1 on validation, a neutral choice for a demo. Any real use would set it from the real
  costs of each kind of mistake.
* **Group inputs are used as features.** The model treats people differently by age band and distance because the rule
  does. Training without them, and measuring what that costs, is left as future work.
"""


def main():
    results = run(gen.load_csv())
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_bytes((json.dumps(results, indent=2) + "\n").encode("utf-8"))
    REPORT_PATH.write_bytes(render(results).encode("utf-8"))
    print(f"Wrote {METRICS_PATH} and {REPORT_PATH} (chosen: {results['chosen']})")


if __name__ == "__main__":
    main()
