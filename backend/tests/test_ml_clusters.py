"""
Week 4, phase 2: exploratory clusters on engagement features (minimal version).

What these tests protect:
* only the 5 engagement features go in: never age band, distance band, the no-show label or the row id;
* the scaler, PCA and K-Means learn from the training pile only;
* k is chosen by the rule fixed in advance (highest silhouette), and weak structure is said plainly;
* descriptions are computed from the numbers and never call clusters people types or risk groups;
* the committed report and JSON are exactly what a fresh run produces;
* the read-only endpoint is for signed-in members only.
"""
import json

import numpy as np
import pytest
from sklearn.metrics import adjusted_rand_score

from ml import features
from ml.data import generate as gen

from .conftest import admin_login, user_login

try:
    from ml import clusters
except ImportError:  # only before phase 2 exists: lets each test fail on its own instead of stopping collection
    clusters = None

URL = "/api/ml/v1/clusters/"
BANNED = ("patient", "risk group", "high risk", "low risk", "high-risk", "low-risk", "type of person", "segment")


@pytest.fixture(scope="module")
def split():
    return features.split_data(gen.load_csv())


@pytest.fixture(scope="module")
def run():
    return clusters.fit_and_evaluate(gen.load_csv())


@pytest.fixture(scope="module")
def results(run):
    return run[0]


@pytest.fixture(scope="module")
def fitted(run):
    return run[1]


# ---------------------------------------------------------------- inputs
def test_only_the_five_engagement_features_go_in():
    assert clusters.CLUSTER_FEATURES == [
        "lead_time_days", "prior_visits", "prior_no_shows", "reminder_sent", "booking_channel"]
    for excluded in ("age_band", "distance_band", features.TARGET, features.ID):
        assert excluded not in clusters.CLUSTER_FEATURES


def test_results_record_the_inputs_used(results):
    assert results["features"] == clusters.CLUSTER_FEATURES


# ---------------------------------------------------------------- training rows only
def test_scaler_pca_and_kmeans_learn_from_the_training_pile_only(fitted, split):
    numbers = split.train[clusters.NUMERIC].astype(float)
    filled = numbers.fillna(numbers.median())
    scaler = fitted["preprocess"].named_transformers_["num"].named_steps["scale"]
    np.testing.assert_allclose(scaler.mean_, filled.mean().to_numpy())
    X_train = fitted["preprocess"].transform(split.train[clusters.CLUSTER_FEATURES])
    np.testing.assert_allclose(fitted["pca"].mean_, X_train.mean(axis=0), atol=1e-12)
    assert len(fitted["kmeans"].labels_) == len(split.train) == 4200


# ---------------------------------------------------------------- elbow, silhouette and the k rule
def test_elbow_and_silhouette_cover_k_2_to_8(results):
    rows = results["elbow"]
    assert [row["k"] for row in rows] == list(range(2, 9))
    inertias = [row["inertia"] for row in rows]
    assert all(a > b for a, b in zip(inertias, inertias[1:]))  # more clusters, smaller inertia
    assert all(-1 <= row["silhouette"] <= 1 for row in rows)


def test_k_rule_picks_the_highest_silhouette_and_ties_go_to_the_smaller_k():
    assert clusters.choose_k({2: 0.30, 3: 0.35, 4: 0.20}) == 3
    assert clusters.choose_k({2: 0.30, 3: 0.30}) == 2


def test_chosen_k_follows_the_rule(results):
    best = max(results["elbow"], key=lambda row: (row["silhouette"], -row["k"]))
    assert results["chosen_k"] == best["k"]


@pytest.mark.parametrize("k, score, weak", [
    (3, 0.62, False),  # reasonable structure, not k=2
    (3, 0.40, True),   # 0.26-0.50: weak
    (4, 0.20, True),   # 0.25 or below: no substantial structure
    (2, 0.62, True),   # k=2 is the smallest allowed k: treated as weak structure
])
def test_structure_is_called_weak_when_silhouette_is_low_or_k_is_2(k, score, weak):
    note = clusters.structure_note(k, score)
    assert ("weak structure" in note) == weak
    assert f"{score:.2f}" in note
    if k == 2:
        assert "k=2" in note


def test_report_states_the_structure_with_the_numbers(results):
    note = clusters.structure_note(results["chosen_k"], results["kmeans"]["silhouette"])
    assert results["structure_note"] == note
    assert note in clusters.render(results)


# ---------------------------------------------------------------- agglomerative comparison
def test_agglomerative_uses_the_chosen_k_and_agreement_is_recomputable(results, fitted):
    agg = results["agglomerative"]
    assert agg["k"] == results["chosen_k"] == len(agg["sizes"])
    assert sum(agg["sizes"]) == 4200
    ari = adjusted_rand_score(fitted["kmeans"].labels_, fitted["agglomerative_labels"])
    assert agg["adjusted_rand_vs_kmeans"] == pytest.approx(ari, abs=1e-4)


def test_validation_rows_are_assigned_but_never_fitted(results):
    v = results["validation"]
    assert v["rows"] == 900 and sum(v["sizes"]) == 900
    assert -1 <= v["silhouette"] <= 1


# ---------------------------------------------------------------- PCA plot points
def test_pca_points_for_the_plot(results):
    pca = results["pca"]
    assert len(pca["explained_variance"]) == 2 and sum(pca["explained_variance"]) <= 1
    points = pca["points"]
    assert 0 < len(points) <= 500
    assert all(len(p) == 3 and 1 <= p[2] <= results["chosen_k"] for p in points)


# ---------------------------------------------------------------- summary and wording
def test_summary_sizes_add_up_and_clusters_are_numbered_largest_first(results):
    summary = results["summary"]
    assert len(summary) == results["chosen_k"]
    assert sum(c["rows"] for c in summary) == 4200
    assert [c["cluster"] for c in summary] == list(range(1, results["chosen_k"] + 1))
    assert [c["rows"] for c in summary] == sorted((c["rows"] for c in summary), reverse=True)


OVERALL = {"mean_lead_time": 12.0, "mean_prior_visits": 3.0, "any_prior_no_show": 0.25, "reminder_yes": 0.65,
           "channel": {"online": 0.5, "phone": 0.3, "in_person": 0.2}}


def test_description_is_computed_from_the_numbers():
    far = {**OVERALL, "mean_lead_time": 31.0, "reminder_yes": 0.95, "channel": {"online": 0.8, "phone": 0.1,
                                                                                  "in_person": 0.1}}
    text = clusters.describe(far, OVERALL)
    assert "much further ahead" in text and "31" in text and "12" in text
    assert "almost always sent a reminder" in text and "mostly books online" in text
    close = {**OVERALL, "mean_lead_time": 3.0, "channel": {"online": 0.2, "phone": 0.7, "in_person": 0.1}}
    text = clusters.describe(close, OVERALL)
    assert "much closer to the date" in text and "mostly books by phone" in text


def test_no_banned_words_in_the_report_or_json(results):
    text = (clusters.render(results) + json.dumps(results)).lower()
    for phrase in BANNED:
        assert phrase not in text, phrase


def test_report_explains_why_clusters_are_exploratory(results):
    report = clusters.render(results)
    assert "## Why these clusters are exploratory" in report
    assert "always finds" in report and "not used for any decision or prediction" in report


def test_no_show_label_is_not_reported_per_cluster(results):
    # `any_prior_no_show` is an input (an earlier missed visit), not the label; no key may carry the label itself.
    label_keys = {features.TARGET, "no_show_rate", "actual_rate", "no_shows"}
    for cluster in results["summary"]:
        assert not label_keys & set(cluster)
    assert not label_keys & set(results["overall"])


# ---------------------------------------------------------------- reproducibility and labels
def test_committed_report_and_json_match_a_fresh_run(results):
    committed = json.loads(clusters.RESULTS_PATH.read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(results))
    report = clusters.REPORT_PATH.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    assert report == clusters.render(results)


def test_results_are_labelled(results):
    assert results["version"] == "clusters-1.0.0"
    assert results["settings"]["seed"] == 42 and results["settings"]["k_range"] == [2, 8]
    assert "not a diagnosis" in results["disclaimer"]


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
    assert res.json() == json.loads(clusters.RESULTS_PATH.read_text(encoding="utf-8"))


def test_post_is_not_allowed(client, user):
    assert user_login(client).status_code == 200
    assert client.post(URL, {}, format="json").status_code == 405


def test_missing_report_is_a_safe_503(client, user, monkeypatch, tmp_path):
    monkeypatch.setattr(clusters, "RESULTS_PATH", tmp_path / "missing.json")
    assert user_login(client).status_code == 200
    res = client.get(URL)
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "report_unavailable"
    assert str(tmp_path) not in res.content.decode()


def test_endpoint_is_throttled(settings):
    from ml.views import ClustersView

    assert ClustersView.throttle_scope == "ml_reports"
    assert "ml_reports" in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
