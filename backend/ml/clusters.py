"""
Week 4, phase 2: exploratory clusters on engagement features (minimal version).

Inputs: 5 engagement features only (how far ahead people book, their previous visits and missed visits, whether a
reminder was sent, how they booked). Never age band, distance band, the no-show label or the row id.

Order of work:
1. the Week 3 split; the preprocessing (training medians, scaling, one-hot), K-Means for k = 2..8 and PCA are
   fitted on the TRAINING pile only;
2. k is chosen by a rule fixed in advance: the highest silhouette on the training pile (ties -> smaller k). The
   features, scaling and k are not tuned to make the clusters look better;
3. Agglomerative (Ward) at that k on the same rows, compared with K-Means;
4. the validation rows are only assigned to the K-Means clusters (a stability check); the test pile is unused.

The clusters are exploratory: they are not kinds of people and are not used for any decision or prediction.
Writes docs/ml/clusters-report.md and backend/ml/reports/clusters.json. Run from backend/:

    python -m ml.clusters
"""
import json
from pathlib import Path

import numpy as np
import sklearn
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from ml import features
from ml.data import generate as gen
from ml.experiment import _rounded

VERSION = "clusters-1.0.0"
RESULTS_PATH = Path(__file__).resolve().parent / "reports" / "clusters.json"
REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "ml" / "clusters-report.md"

NUMERIC = ["lead_time_days", "prior_visits", "prior_no_shows"]
CATEGORICAL = ["reminder_sent", "booking_channel"]
CLUSTER_FEATURES = NUMERIC + CATEGORICAL
K_RANGE = range(2, 9)
SEED = 42
N_INIT = 10
PLOT_POINTS = 500
CHANNEL_WORDS = {"online": "online", "phone": "by phone", "in_person": "in person"}

DISCLAIMER = (
    "Exploratory analysis of synthetic data. Not medical advice and not a diagnosis. The clusters are not kinds of "
    "people and are not used for any decision or prediction."
)


# ---------------------------------------------------------------- building blocks (unit-tested)
def build_preprocessor():
    """Unfitted. Numbers: training median for blanks, then scaling. Categories: blank -> 'missing', then one-hot."""
    numeric = Pipeline([
        ("to_float", FunctionTransformer(features.as_float, feature_names_out="one-to-one")),
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("to_text", FunctionTransformer(features.as_text, feature_names_out="one-to-one")),
        ("impute", SimpleImputer(strategy="constant", fill_value=features.MISSING)),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer([("num", numeric, NUMERIC), ("cat", categorical, CATEGORICAL)])


def choose_k(silhouettes):
    """The rule fixed in advance: the highest silhouette; on a tie the smaller k."""
    return max(silhouettes, key=lambda k: (silhouettes[k], -k))


def structure_label(score):
    """Kaufman and Rousseeuw's usual reading of an average silhouette."""
    if score > 0.70:
        return "strong"
    if score > 0.50:
        return "reasonable"
    if score > 0.25:
        return "weak"
    return "no substantial"


def structure_note(k, score):
    label = structure_label(score)
    text = f"The chosen k is {k} with an average silhouette of {score:.2f}, which reads as {label} structure"
    reasons = []
    if label in ("weak", "no substantial"):
        reasons.append(f"a silhouette of {score:.2f} is low (0.50 or below)")
    if k == 2:
        reasons.append("k=2 is the smallest k allowed, so it can win simply because no larger number of groups "
                       "fits better")
    if reasons:
        return (f"{text}. We treat this as weak structure: {'; and '.join(reasons)}. The groups below are a "
                "convenient way to summarise the rows, not evidence of natural groups.")
    return f"{text}. Even so, the clusters remain exploratory (see below)."


def describe(stats, overall):
    """Plain words from the numbers, each compared with the training average. Booking behaviour only."""
    parts = []
    lead, avg_lead = stats["mean_lead_time"], overall["mean_lead_time"]
    ratio = lead / avg_lead if avg_lead else 1.0
    if ratio >= 1.5:
        parts.append(f"books much further ahead than average ({lead:.0f} vs {avg_lead:.0f} days)")
    elif ratio >= 1.15:
        parts.append(f"books somewhat further ahead than average ({lead:.0f} vs {avg_lead:.0f} days)")
    elif ratio <= 0.67:
        parts.append(f"books much closer to the date than average ({lead:.0f} vs {avg_lead:.0f} days)")
    elif ratio <= 0.87:
        parts.append(f"books somewhat closer to the date than average ({lead:.0f} vs {avg_lead:.0f} days)")
    else:
        parts.append(f"books about as far ahead as average ({lead:.0f} days)")

    visits, avg_visits = stats["mean_prior_visits"], overall["mean_prior_visits"]
    if visits - avg_visits >= 1:
        parts.append(f"more previous visits than average ({visits:.1f} vs {avg_visits:.1f})")
    elif avg_visits - visits >= 1:
        parts.append(f"fewer previous visits than average ({visits:.1f} vs {avg_visits:.1f})")

    missed, avg_missed = stats["any_prior_no_show"], overall["any_prior_no_show"]
    if missed - avg_missed >= 0.15:
        parts.append(f"more often has an earlier missed visit ({missed:.0%} vs {avg_missed:.0%})")
    elif avg_missed - missed >= 0.15:
        parts.append(f"less often has an earlier missed visit ({missed:.0%} vs {avg_missed:.0%})")

    reminder = stats["reminder_yes"]
    if reminder >= 0.9:
        parts.append("almost always sent a reminder")
    elif reminder <= 0.1:
        parts.append("rarely sent a reminder")
    elif abs(reminder - overall["reminder_yes"]) >= 0.2:
        parts.append(f"sent a reminder {reminder:.0%} of the time (average {overall['reminder_yes']:.0%})")

    channel, share = max(stats["channel"].items(), key=lambda item: item[1])
    parts.append(f"mostly books {CHANNEL_WORDS[channel]}" if share >= 0.6 else "mixed booking channels")
    text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."


def _stats(pile):
    """Booking-behaviour numbers for a group of rows (blanks ignored where a value is unknown)."""
    prior_visits = pile["prior_visits"].astype(float)
    prior_no_shows = pile["prior_no_shows"].astype(float)
    known = prior_no_shows.notna()
    return {
        "mean_lead_time": float(pile["lead_time_days"].mean()),
        "mean_prior_visits": float(prior_visits.mean()),
        "any_prior_no_show": float((prior_no_shows[known] > 0).mean()),
        "reminder_yes": float((pile["reminder_sent"] == "yes").mean()),
        "channel": {c: float((pile["booking_channel"] == c).mean()) for c in CHANNEL_WORDS},
    }


def _numbered_by_size(labels):
    """Relabel clusters 1..k, largest first, so the numbering is stable and readable."""
    counts = np.bincount(labels)
    order = np.argsort(-counts, kind="stable")
    mapping = np.empty_like(order)
    mapping[order] = np.arange(1, len(order) + 1)
    return mapping[labels]


def _sizes(labels, k):
    return [int((labels == c).sum()) for c in range(1, k + 1)]


# ---------------------------------------------------------------- the run
def run(frame):
    return fit_and_evaluate(frame)[0]


def fit_and_evaluate(frame):
    """Returns (results, fitted pieces). Everything is fitted on the training pile only."""
    split = features.split_data(frame)
    train, validation = split.train, split.validation
    preprocess = build_preprocessor().fit(train[CLUSTER_FEATURES])
    X_train = preprocess.transform(train[CLUSTER_FEATURES])

    elbow, fitted_by_k = [], {}
    for k in K_RANGE:
        km = KMeans(n_clusters=k, n_init=N_INIT, random_state=SEED).fit(X_train)
        fitted_by_k[k] = km
        elbow.append({"k": k, "inertia": float(km.inertia_),
                      "silhouette": float(silhouette_score(X_train, km.labels_))})
    chosen = choose_k({row["k"]: row["silhouette"] for row in elbow})
    kmeans = fitted_by_k[chosen]
    km_labels = _numbered_by_size(kmeans.labels_)
    km_silhouette = next(row["silhouette"] for row in elbow if row["k"] == chosen)

    agg_raw = AgglomerativeClustering(n_clusters=chosen, linkage="ward").fit_predict(X_train)
    agg_labels = _numbered_by_size(agg_raw)

    val_raw = kmeans.predict(preprocess.transform(validation[CLUSTER_FEATURES]))
    # Same numbering as the training clusters: map each raw K-Means id to its training cluster number.
    raw_to_number = {int(raw): int(num) for raw, num in zip(kmeans.labels_, km_labels)}
    val_labels = np.array([raw_to_number[int(r)] for r in val_raw])
    X_val = preprocess.transform(validation[CLUSTER_FEATURES])

    pca = PCA(n_components=2, random_state=SEED).fit(X_train)
    coords = pca.transform(X_train)
    picked = np.sort(np.random.default_rng(SEED).choice(len(train), size=PLOT_POINTS, replace=False))
    points = [[round(float(coords[i, 0]), 3), round(float(coords[i, 1]), 3), int(km_labels[i])] for i in picked]

    overall = _stats(train)
    summary = []
    for c in range(1, chosen + 1):
        part = train[km_labels == c]
        stats = _stats(part)
        summary.append({"cluster": c, "rows": len(part), "share": len(part) / len(train), **stats,
                        "description": describe(stats, overall)})

    results = _rounded({
        "version": VERSION,
        "disclaimer": DISCLAIMER,
        "features": CLUSTER_FEATURES,
        "settings": {"split_seed": features.SPLIT_SEED, "seed": SEED, "n_init": N_INIT,
                     "k_range": [K_RANGE.start, K_RANGE.stop - 1], "plot_points": PLOT_POINTS,
                     "scikit_learn": sklearn.__version__},
        "elbow": elbow,
        "chosen_k": chosen,
        "structure_note": structure_note(chosen, round(km_silhouette, 4)),
        "kmeans": {"silhouette": km_silhouette, "sizes": _sizes(km_labels, chosen)},
        "agglomerative": {
            "k": chosen, "linkage": "ward", "silhouette": float(silhouette_score(X_train, agg_labels)),
            "sizes": _sizes(agg_labels, chosen),
            "adjusted_rand_vs_kmeans": float(adjusted_rand_score(km_labels, agg_labels)),
        },
        "validation": {"rows": len(validation), "sizes": _sizes(val_labels, chosen),
                       "silhouette": float(silhouette_score(X_val, val_labels))},
        "pca": {"explained_variance": [float(v) for v in pca.explained_variance_ratio_], "points": points},
        "overall": overall,
        "summary": summary,
    })
    fitted = {"preprocess": preprocess, "kmeans": kmeans, "pca": pca, "agglomerative_labels": agg_labels}
    return results, fitted


# ---------------------------------------------------------------- the report
def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    return "\n".join(lines + ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows])


def render(results):
    k, s = results["chosen_k"], results["settings"]
    elbow_rows = [[row["k"], f"{row['inertia']:.0f}", f"{row['silhouette']:.3f}", "chosen" if row["k"] == k else ""]
                  for row in results["elbow"]]
    summary_rows = [
        [c["cluster"], c["rows"], f"{c['share']:.0%}", f"{c['mean_lead_time']:.1f}", f"{c['mean_prior_visits']:.1f}",
         f"{c['any_prior_no_show']:.0%}", f"{c['reminder_yes']:.0%}", f"{c['channel']['online']:.0%}",
         f"{c['channel']['phone']:.0%}", f"{c['channel']['in_person']:.0%}"]
        for c in results["summary"]
    ]
    o = results["overall"]
    summary_rows.append(["All", sum(c["rows"] for c in results["summary"]), "100%", f"{o['mean_lead_time']:.1f}",
                         f"{o['mean_prior_visits']:.1f}", f"{o['any_prior_no_show']:.0%}", f"{o['reminder_yes']:.0%}",
                         f"{o['channel']['online']:.0%}", f"{o['channel']['phone']:.0%}",
                         f"{o['channel']['in_person']:.0%}"])
    descriptions = "\n".join(f"* **Cluster {c['cluster']}** ({c['rows']} rows): {c['description']}"
                             for c in results["summary"])
    km, agg, val, pca = results["kmeans"], results["agglomerative"], results["validation"], results["pca"]
    ev = pca["explained_variance"]
    compare_rows = [
        ["K-Means", f"{km['silhouette']:.3f}", " / ".join(str(n) for n in km["sizes"])],
        ["Agglomerative (Ward)", f"{agg['silhouette']:.3f}", " / ".join(str(n) for n in agg["sizes"])],
    ]

    return f"""# Week 4 exploratory clusters ({results['version']})

> **{results['disclaimer']}**

Generated by `python -m ml.clusters` from the committed dataset; a test checks this file matches a fresh run.
Machine-readable copy: [`backend/ml/reports/clusters.json`](../../backend/ml/reports/clusters.json).

## What went in

* **5 engagement features:** {', '.join(f'`{f}`' for f in results['features'])}. Age band, distance band, the
  no-show label and the row id are left out, and no no-show rate is reported per cluster.
* Numbers: the training median fills blanks, then scaling to mean 0 and spread 1. `reminder_sent` and
  `booking_channel`: a blank becomes "missing", then one column per value (0 or 1).
* Everything (scaling, K-Means, PCA, Agglomerative) is fitted on the {sum(km['sizes'])} training rows only
  (Week 3 split, seed {s['split_seed']}). K-Means: seed {s['seed']}, {s['n_init']} random starts per k.
* **The k rule was fixed before the results were seen:** the highest average silhouette for k = {s['k_range'][0]}
  to {s['k_range'][1]} (ties go to the smaller k). Features, scaling and k were not adjusted afterwards.

## Elbow and silhouette (training rows)

{_table(["k", "Inertia (elbow)", "Average silhouette", ""], elbow_rows)}

Inertia always falls as k grows; the "elbow" is where it stops falling quickly. The silhouette (from -1 to 1) says
how much closer each row is to its own cluster than to the next one.

**{results['structure_note']}**

## K-Means compared with Agglomerative (k = {k})

{_table(["Method", "Average silhouette", "Cluster sizes (largest first)"], compare_rows)}

Agreement between the two methods (adjusted Rand index, 1 = identical groups, 0 = no better than chance):
**{agg['adjusted_rand_vs_kmeans']:.3f}**.

Stability check: the {val['rows']} validation rows, assigned to the nearest K-Means cluster without refitting, have
an average silhouette of **{val['silhouette']:.3f}** (sizes {' / '.join(str(n) for n in val['sizes'])}).

## Cluster summary (K-Means, training rows)

{_table(["Cluster", "Rows", "Share", "Avg lead days", "Avg previous visits", "Any earlier missed visit",
         "Reminder sent", "Online", "Phone", "In person"], summary_rows)}

{descriptions}

These sentences describe booking behaviour in the synthetic rows, compared with the training average. They say
nothing about who anyone is.

## 2D PCA view

PCA squeezes the scaled inputs into two directions for a picture. The first two directions keep
{ev[0]:.0%} and {ev[1]:.0%} of the spread ({ev[0] + ev[1]:.0%} together), so the plot shows only part of the
picture: clusters that overlap in 2D may be apart in the full data, and the reverse. The dashboard plots
{len(pca['points'])} seeded sample points, coloured by K-Means cluster.

## Why these clusters are exploratory

* **K-Means always finds k groups**, even in data with no real groups. A cluster existing is not evidence of
  anything; the silhouette above says how separated the groups really are.
* The groups depend on choices: which features went in, how they were scaled, k and the seed. Different
  reasonable choices give different groups.
* The data is synthetic and follows a rule we wrote, so the groups describe that rule's booking patterns, not real
  clinics or real people.
* The clusters are **not used for any decision or prediction**, are not kinds of people, and should not be used to
  treat anyone differently.
"""


def main():
    results = run(gen.load_csv())
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_bytes((json.dumps(results, indent=2) + "\n").encode("utf-8"))
    REPORT_PATH.write_bytes(render(results).encode("utf-8"))
    print(f"Wrote {RESULTS_PATH} and {REPORT_PATH} (chosen k: {results['chosen_k']})")


if __name__ == "__main__":
    main()
