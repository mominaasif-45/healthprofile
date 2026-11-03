"""
Week 3, phase 3: baseline vs improved models, metrics, threshold, leakage alarm, group results.

Fast unit tests run on tiny examples. The tests that need the full experiment share one run (the
`results` fixture); set ML_SKIP_SLOW=1 to skip them locally. They run by default.
"""
import json
import os

import numpy as np
import pytest
from sklearn.compose import ColumnTransformer
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline

from ml import evaluate, experiment, features, models
from ml.data import generate as gen

slow = pytest.mark.skipif(os.environ.get("ML_SKIP_SLOW") == "1", reason="ML_SKIP_SLOW=1 set")


@pytest.fixture(scope="module")
def frame():
    return gen.load_csv()


@pytest.fixture(scope="module")
def split(frame):
    return features.split_data(frame)


@pytest.fixture(scope="module")
def results(frame):
    return experiment.run(frame)


# ---------------------------------------------------------------- the candidates
def test_every_candidate_is_one_pipeline_starting_with_the_preprocessor():
    for name in models.CANDIDATES:
        pipe = models.make_pipeline(name)
        assert isinstance(pipe, Pipeline)
        assert pipe.steps[0][0] == "preprocess" and isinstance(pipe.steps[0][1], ColumnTransformer)
        assert pipe.steps[-1][0] == "model"


def test_baseline_gives_everyone_the_training_no_show_rate(split):
    fitted, _ = models.fit_candidate("baseline", split.train)
    p = fitted.predict_proba(features.features_of(split.validation))[:, 1]
    assert np.allclose(p, split.train["no_show"].mean())
    assert roc_auc_score(features.target_of(split.validation), p) == 0.5


def test_model_is_trained_on_the_training_pile_only(split):
    fitted, _ = models.fit_candidate("logistic_regression", split.train)
    impute = fitted.named_steps["preprocess"].named_transformers_["num"].named_steps["impute"]
    medians = split.train[features.NUMERIC].astype(float).median().to_numpy()
    np.testing.assert_allclose(impute.statistics_, medians)


# ---------------------------------------------------------------- metrics and threshold
Y = np.array([0, 0, 1, 1, 0, 1])
P = np.array([0.10, 0.40, 0.35, 0.80, 0.20, 0.70])


def test_threshold_metrics_match_a_hand_calculation():
    m = evaluate.threshold_metrics(Y, P, 0.5)  # flagged: 0.80 and 0.70, both real no-shows
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (2, 0, 1, 3)
    assert m["precision"] == 1.0 and m["recall"] == pytest.approx(2 / 3)
    assert m["f1"] == pytest.approx(0.8) and m["balanced_accuracy"] == pytest.approx((2 / 3 + 1) / 2)


def test_threshold_is_the_best_f1_and_ties_go_to_the_higher_threshold():
    """F1 is 0.857 for every threshold from 0.21 to 0.35 (3 caught, 1 false alarm); the tie goes to 0.35."""
    assert evaluate.choose_threshold(Y, P) == 0.35


# ---------------------------------------------------------------- the leakage alarm
def test_alarm_allows_sampling_luck_within_the_margin():
    evaluate.check_leakage(0.680, ceiling=0.657, where="test")  # 0.023 above: within the 0.03 margin


@pytest.mark.parametrize("auc, ceiling", [(0.688, 0.657), (0.91, 0.95)])
def test_alarm_goes_off_above_the_margin_or_above_0_90(auc, ceiling):
    with pytest.raises(evaluate.LeakageAlarm):
        evaluate.check_leakage(auc, ceiling=ceiling, where="validation")


def test_alarm_catches_a_planted_copy_of_the_answer(frame):
    """Disguise the label as a feature (reminder_sent = 'yes' exactly when no_show = 1): the run must stop."""
    leaky = frame.copy()
    leaky["reminder_sent"] = np.where(leaky["no_show"] == 1, "yes", "no")
    with pytest.raises(evaluate.LeakageAlarm):
        experiment.run(leaky)


# ---------------------------------------------------------------- choosing a model
@pytest.mark.parametrize(
    "interval, expected",
    [
        ((-0.010, 0.030), "logistic_regression"),  # not clearly better: keep the simple model
        ((-0.050, -0.010), "logistic_regression"),  # clearly worse
        ((0.005, 0.040), "gradient_boosting"),      # clearly better: it earns its complexity
    ],
)
def test_selection_rule_needs_a_clear_win_for_the_complex_model(interval, expected):
    assert evaluate.select_model(interval) == expected


# ---------------------------------------------------------------- the full experiment
@slow
def test_no_model_beats_the_ceiling_by_more_than_the_margin(results):
    for pile in ("validation", "test"):
        for name in models.CANDIDATES:
            auc = results[pile][name]["roc_auc"]
            assert auc <= results["ceilings"][pile] + evaluate.LEAKAGE_MARGIN and auc <= evaluate.MAX_PLAUSIBLE_AUC


@slow
def test_both_models_clearly_beat_the_baseline(results):
    for name in ("logistic_regression", "gradient_boosting"):
        assert results["comparisons"][f"{name}_vs_baseline"]["low"] > 0, name


@slow
def test_chosen_model_follows_the_rule_and_its_threshold_is_frozen(results):
    comparison = results["comparisons"]["gradient_boosting_vs_logistic_regression"]
    assert results["chosen"] == evaluate.select_model((comparison["low"], comparison["high"]))
    chosen = results["chosen"]
    assert results["test"][chosen]["threshold"] == results["validation"][chosen]["threshold"]


@slow
def test_group_table_counts_every_row_and_flags_small_groups(results, split):
    for pile_name, pile in (("validation", split.validation), ("test", split.test)):
        rows = results["groups"][pile_name]
        for column in evaluate.GROUP_COLUMNS:
            mine = [r for r in rows if r["column"] == column]
            assert sum(r["rows"] for r in mine) == len(pile)
            assert sum(r["no_shows"] for r in mine) == int(pile["no_show"].sum())
            for r in mine:
                assert r["small"] == (r["rows"] < evaluate.SMALL_ROWS or r["no_shows"] < evaluate.SMALL_NO_SHOWS)


@slow
def test_committed_report_and_metrics_match_a_fresh_run(results):
    committed = json.loads(experiment.METRICS_PATH.read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(results))
    report = experiment.REPORT_PATH.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    assert report == experiment.render(results)


# ---------------------------------------------------------------- the reminder trade-off at the threshold (mentor review)
# Made-up counts, deliberately unlike the real ones: the paragraph must be computed, not typed in.
TOY_SCORES = {"tp": 7, "fp": 13, "fn": 5, "tn": 15, "precision": 0.35, "recall": 7 / 12, "threshold": 0.3}


def test_reminder_paragraph_is_computed_from_the_counts():
    text = experiment.reminder_tradeoff(TOY_SCORES)
    for part in [
        "**What the 0.30 line means.**",
        "chosen on the validation pile",
        "suggests an extra reminder, not a certain no-show",
        "flagged 20 of 40 appointments",
        "7 were real no-shows (precision 35.0%)",
        "the other 13 would get a reminder they did not need",
        "caught 7 of the 12 no-shows (recall 58.3%)",
        "so 5 missed appointments would get no extra reminder",
    ]:
        assert part in text, part
    assert "patient" not in text.lower()


def test_committed_report_explains_the_reminder_trade_off():
    """Fast check on the committed files: section 6 carries the paragraph built from metrics.json."""
    results = json.loads(experiment.METRICS_PATH.read_text(encoding="utf-8"))
    expected = experiment.reminder_tradeoff(results["test"][results["chosen"]])
    report = experiment.REPORT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    section_6 = report.split("## 6. The decision threshold")[1].split("## 7.")[0]
    assert expected in section_6
    assert "patient" not in report.lower()
