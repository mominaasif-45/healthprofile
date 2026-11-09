"""
Week 4, phase 1: the supervised comparison workbench (a report, not a new shipped model).

What these tests protect:
* every candidate is one reproducible Pipeline, fitted on the training pile only;
* cross-validation is stratified and uses training rows only;
* the comparison and any choice use the validation pile only; the test pile (already used in Week 3)
  is reported afterwards and never used to choose;
* the committed report and JSON are exactly what a fresh run produces;
* the Week 3 model (noshow-1.0.0) and its metrics stay untouched;
* the read-only dashboard endpoint is for signed-in members only.

The tests that need the full workbench share one run (the `run` fixture, a few minutes on one CPU core);
set ML_SKIP_SLOW=1 to skip them locally, as in Week 3. They run by default and in CI.
"""
import hashlib
import json
import os

import numpy as np
import pandas as pd
import pytest
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.compose import ColumnTransformer
from sklearn.inspection import permutation_importance
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline

from ml import artifact, experiment, features, models
from ml.data import generate as gen

from .conftest import admin_login, user_login

try:
    from ml import workbench
except ImportError:  # only before phase 1 exists: lets each test fail on its own instead of stopping collection
    workbench = None

slow = pytest.mark.skipif(os.environ.get("ML_SKIP_SLOW") == "1", reason="ML_SKIP_SLOW=1 set")
URL = "/api/ml/v1/workbench/"
NOSHOW_SHA256 = "d69f7723b34fe773da3eb09841304a050bb72410654c00487b1a4f242fec8218"
WEEK3_METRICS_SHA256 = "dece33f40c2942e0ca6bb80b3151095ed93cd2e18cee39c10963f3aa7be84461"
TRAINED = ("logistic_regression", "random_forest", "gradient_boosting")
STRONG_RULE_INPUTS = {"lead_time_days", "prior_no_shows", "reminder_sent"}  # the rule's three largest terms


@pytest.fixture(scope="module")
def frame():
    return gen.load_csv()


@pytest.fixture(scope="module")
def split(frame):
    return features.split_data(frame)


@pytest.fixture(scope="module")
def run(frame):
    """(results, fitted pipelines), computed once for the whole module."""
    return workbench.fit_and_evaluate(frame)


@pytest.fixture(scope="module")
def results(run):
    return run[0]


@pytest.fixture(scope="module")
def fitted(run):
    return run[1]


# ---------------------------------------------------------------- the candidates
def test_workbench_compares_four_models_and_week3_candidates_are_unchanged():
    assert models.WORKBENCH_CANDIDATES == ("baseline", "logistic_regression", "random_forest", "gradient_boosting")
    assert models.CANDIDATES == ("baseline", "logistic_regression", "gradient_boosting")


def test_random_forest_is_one_pipeline_starting_with_the_preprocessor():
    pipe = models.make_pipeline("random_forest")
    assert isinstance(pipe, Pipeline)
    assert [name for name, _ in pipe.steps] == ["preprocess", "model"]
    assert isinstance(pipe.named_steps["preprocess"], ColumnTransformer)
    rf = pipe.named_steps["model"]
    assert rf.random_state == models.SEED and rf.n_jobs == 1  # seeded, one CPU core (low memory)


@slow
def test_random_forest_learns_its_preprocessing_from_the_training_pile_only(fitted, split):
    impute = fitted["random_forest"].named_steps["preprocess"].named_transformers_["num"].named_steps["impute"]
    medians = split.train[features.NUMERIC].astype(float).median().to_numpy()
    np.testing.assert_allclose(impute.statistics_, medians)


# ---------------------------------------------------------------- cross-validation
def test_cross_validation_is_stratified_shuffled_and_seeded():
    cv = models.cv_splitter()
    assert isinstance(cv, StratifiedKFold)
    assert (cv.n_splits, cv.shuffle, cv.random_state) == (models.CV_FOLDS, True, models.SEED)


def test_cross_validation_folds_use_training_rows_only_and_keep_the_no_show_rate(split):
    folds = workbench.cv_folds(split.train)
    assert len(folds) == models.CV_FOLDS
    held_out = np.concatenate([test_idx for _, test_idx in folds])
    assert sorted(held_out) == list(range(len(split.train)))  # positions inside the training pile, each once
    y = features.target_of(split.train).to_numpy()
    for _, test_idx in folds:
        assert abs(y[test_idx].mean() - y.mean()) < 0.01


@slow
def test_every_model_reports_five_fold_scores_on_the_training_pile(results):
    for name in models.WORKBENCH_CANDIDATES:
        cv = results["models"][name]["cv"]
        assert cv["rows"] == 4200
        for metric in ("roc_auc", "pr_auc"):
            assert len(cv[metric]["folds"]) == models.CV_FOLDS
            assert cv[metric]["mean"] == pytest.approx(np.mean(cv[metric]["folds"]), abs=1e-4)


# ---------------------------------------------------------------- tuning
@slow
def test_random_forest_tried_ten_settings_and_reports_the_true_best(results):
    tries = results["rf_search"]
    assert len(tries) == models.RF_SEARCH_TRIES == 10
    best = max(tries, key=lambda t: t["cv_pr_auc_mean"])
    tuning = results["models"]["random_forest"]["tuning"]
    assert tuning["best_params"] == best["params"]
    assert tuning["cv_pr_auc"] == best["cv_pr_auc_mean"]


# ---------------------------------------------------------------- validation metrics
@slow
def test_confusion_matrices_cover_the_validation_pile_and_match_scikit_learn(results, fitted, split):
    y = features.target_of(split.validation).to_numpy()
    for name in models.WORKBENCH_CANDIDATES:
        v = results["models"][name]["validation"]
        assert v["tp"] + v["fp"] + v["fn"] + v["tn"] == len(split.validation) == 900
        p = fitted[name].predict_proba(features.features_of(split.validation))[:, 1]
        tn, fp, fn, tp = confusion_matrix(y, p >= v["threshold"], labels=[0, 1]).ravel()
        assert (v["tn"], v["fp"], v["fn"], v["tp"]) == (tn, fp, fn, tp)


@slow
def test_train_versus_validation_gap_and_overfitting_flag(results):
    for name in models.WORKBENCH_CANDIDATES:
        m = results["models"][name]
        gap = m["train"]["pr_auc"] - m["validation"]["pr_auc"]
        assert m["gap"]["pr_auc"] == pytest.approx(gap, abs=1e-4)
        assert m["gap"]["overfit"] == (gap > workbench.OVERFIT_GAP)


@slow
def test_no_model_trips_the_leakage_alarm(results):
    for pile in ("validation", "test"):
        ceiling = results["ceilings"][pile]
        for name in models.WORKBENCH_CANDIDATES:
            scores = results["models"][name] if pile == "validation" else results["test"]
            auc = (scores["validation"] if pile == "validation" else scores[name])["roc_auc"]
            assert auc <= ceiling + 0.03 and auc <= 0.90


# ---------------------------------------------------------------- choice on validation only
def test_best_model_is_chosen_from_validation_scores_only():
    validation = {"baseline": {"pr_auc": 0.9}, "logistic_regression": {"pr_auc": 0.40},
                  "random_forest": {"pr_auc": 0.45}, "gradient_boosting": {"pr_auc": 0.42}}
    assert workbench.best_on_validation(validation) == "random_forest"  # the baseline never counts


@slow
def test_choice_matches_validation_and_test_is_reported_for_all_four(results):
    trained = {n: results["models"][n]["validation"] for n in TRAINED}
    assert results["best_on_validation"] == max(trained, key=lambda n: trained[n]["pr_auc"])
    assert set(results["test"]) == set(models.WORKBENCH_CANDIDATES)
    for name in models.WORKBENCH_CANDIDATES:  # test uses the thresholds frozen on validation
        assert results["test"][name]["threshold"] == results["models"][name]["validation"]["threshold"]


def test_report_states_that_the_test_pile_was_reused_and_not_used_to_choose():
    text = workbench.TEST_PILE_NOTE
    assert "already used in Week 3" in text and "validation pile only" in text and "not used to choose" in text


# ---------------------------------------------------------------- permutation importance
class _OnlyColumnA(ClassifierMixin, BaseEstimator):
    """A toy model whose probability depends on column `a` only."""

    def fit(self, X, y):
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X):
        p = 1 / (1 + np.exp(-np.asarray(X["a"], dtype=float)))
        return np.column_stack([1 - p, p])


def test_importance_measures_what_the_model_uses():
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"a": rng.normal(size=400), "b": rng.normal(size=400)})
    y = (X["a"] + 0.3 * rng.normal(size=400) > 0).astype(int)
    table = workbench.importance_table(_OnlyColumnA().fit(X, y), X, y)
    by_feature = {row["feature"]: row for row in table}
    assert by_feature["a"]["mean"] > 0.1
    assert by_feature["b"]["mean"] == 0 and by_feature["b"]["sd"] == 0  # shuffling an unused column changes nothing
    assert [row["feature"] for row in table] == ["a", "b"]  # most important first


@slow
def test_importance_covers_the_ten_inputs_on_the_validation_pile(results, fitted, split):
    for name in TRAINED:
        table = results["importance"][name]
        assert sorted(row["feature"] for row in table) == sorted(features.FEATURES)
        assert STRONG_RULE_INPUTS & {row["feature"] for row in table[:2]}
    # Recompute one model's importance on the validation pile with the same seed: it must match exactly.
    X, y = features.features_of(split.validation), features.target_of(split.validation)
    raw = permutation_importance(fitted["logistic_regression"], X, y, scoring="average_precision",
                                 n_repeats=workbench.PERMUTATION_REPEATS, random_state=models.SEED, n_jobs=1)
    expected = dict(zip(features.FEATURES, np.round(raw.importances_mean, 4)))
    for row in results["importance"]["logistic_regression"]:
        assert row["mean"] == pytest.approx(expected[row["feature"]], abs=1e-4)


# ---------------------------------------------------------------- false positives and negatives
@slow
def test_error_inspection_uses_the_best_model_on_validation(results):
    errors = results["errors"]
    best = results["best_on_validation"]
    assert errors["model"] == best
    assert errors["threshold"] == results["models"][best]["validation"]["threshold"]
    assert sum(box["rows"] for box in errors["profile"]) == 900
    assert all(r["no_show"] == 0 and r["p"] >= errors["threshold"] for r in errors["false_alarms"])
    assert all(r["no_show"] == 1 and r["p"] < errors["threshold"] for r in errors["misses"])
    assert 0 < len(errors["false_alarms"]) <= 10 and 0 < len(errors["misses"]) <= 10


# ---------------------------------------------------------------- reproducibility and labels
@slow
def test_committed_report_and_json_match_a_fresh_run(results):
    committed = json.loads(workbench.RESULTS_PATH.read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(results))
    report = workbench.REPORT_PATH.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    assert report == workbench.render(results)


@slow
def test_results_are_labelled_with_version_seeds_and_disclaimer(results):
    assert results["version"] == "workbench-1.0.0"
    assert results["settings"]["model_seed"] == models.SEED and results["settings"]["split_seed"] == 42
    assert "not a diagnosis" in results["disclaimer"] and "noshow-1.0.0" in results["disclaimer"]


# ---------------------------------------------------------------- Week 3 untouched
def _normalised_sha256(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_week3_model_and_metrics_are_untouched():
    assert artifact.EXPECTED_SHA256 == NOSHOW_SHA256
    assert hashlib.sha256(artifact.MODEL_PATH.read_bytes()).hexdigest() == NOSHOW_SHA256
    assert _normalised_sha256(experiment.METRICS_PATH) == WEEK3_METRICS_SHA256


# ---------------------------------------------------------------- the read-only endpoint
def test_signed_out_is_401(client, db):
    res = client.get(URL)
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "not_authenticated"


def test_admin_session_is_401_like_every_member_route(client, admin):
    assert admin_login(client).status_code == 200
    assert client.get(URL).status_code == 401


def test_member_gets_the_committed_report(client, user):
    assert user_login(client).status_code == 200
    res = client.get(URL)
    assert res.status_code == 200
    data = res.json()
    assert data == json.loads(workbench.RESULTS_PATH.read_text(encoding="utf-8"))
    assert data["version"] == "workbench-1.0.0" and "not a diagnosis" in data["disclaimer"]


def test_post_is_not_allowed(client, user):
    assert user_login(client).status_code == 200
    assert client.post(URL, {}, format="json").status_code == 405


def test_missing_report_is_a_safe_503(client, user, monkeypatch, tmp_path):
    monkeypatch.setattr(workbench, "RESULTS_PATH", tmp_path / "missing.json")
    assert user_login(client).status_code == 200
    res = client.get(URL)
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "report_unavailable"
    assert str(tmp_path) not in res.content.decode()  # no file paths in the error


def test_endpoint_is_throttled(settings):
    from ml.views import WorkbenchView

    assert WorkbenchView.throttle_scope == "ml_reports"
    assert "ml_reports" in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]


# ---------------------------------------------------------------- honest wording, computed from the numbers
def _toy_models(lr, rf, gb, cv=0.40):
    def model(val_pr, train_pr):
        return {"validation": {"pr_auc": val_pr}, "train": {"pr_auc": train_pr},
                "cv": {"pr_auc": {"mean": cv}}, "gap": {"pr_auc": train_pr - val_pr}}
    return {"baseline": model(0.2, 0.2), "logistic_regression": model(*lr), "random_forest": model(*rf),
            "gradient_boosting": model(*gb)}


def test_tie_note_says_practically_tied_when_the_lead_is_small():
    tied = workbench.tie_note(_toy_models((0.30, 0.31), (0.325, 0.60), (0.324, 0.42)))
    assert "practically tied" in tied and "Random forest" in tied and "Gradient boosting" in tied
    clear = workbench.tie_note(_toy_models((0.30, 0.31), (0.40, 0.60), (0.32, 0.42)))
    assert "practically tied" not in clear


def test_harder_pile_note_appears_only_when_every_model_is_below_its_cv_score():
    assert "harder" in workbench.harder_pile_note(_toy_models((0.30, 0.31), (0.32, 0.6), (0.31, 0.4), cv=0.35))
    assert workbench.harder_pile_note(_toy_models((0.30, 0.31), (0.36, 0.6), (0.31, 0.4), cv=0.35)) == ""


def test_negative_importance_note_names_inputs_clearly_below_zero():
    importance = {"random_forest": [{"feature": "a", "mean": 0.05, "sd": 0.01},
                                    {"feature": "noise", "mean": -0.003, "sd": 0.003},
                                    {"feature": "channel", "mean": -0.02, "sd": 0.006}]}
    note = workbench.negative_importance_note(importance)
    assert "channel" in note and "noise" not in note
    assert workbench.negative_importance_note({"random_forest": importance["random_forest"][:2]}) == ""


def test_test_ranking_note_only_reports_and_never_changes_the_choice():
    results = {"best_on_validation": "random_forest",
               "test": {"baseline": {"pr_auc": 0.2}, "logistic_regression": {"pr_auc": 0.34},
                        "random_forest": {"pr_auc": 0.33}, "gradient_boosting": {"pr_auc": 0.32}}}
    note = workbench.ranking_on_test_note(results)
    assert "Logistic regression" in note and "not used to choose" in note
    assert results["best_on_validation"] == "random_forest"
