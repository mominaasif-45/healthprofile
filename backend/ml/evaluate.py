"""
Metrics, the decision threshold, bootstrap intervals, per-group results and the leakage alarm.

Every rule here was fixed BEFORE looking at results (Week 3 phase 3 plan):
* threshold: the best F1 on the validation pile, ties to the higher threshold, then frozen;
* leakage alarm: a model may not beat the rule's own score on the same pile by more than LEAKAGE_MARGIN,
  and no ROC-AUC may exceed MAX_PLAUSIBLE_AUC;
* model choice: gradient boosting only if its PR-AUC advantage over logistic regression has a paired
  95% bootstrap interval entirely above zero; otherwise the simpler logistic regression.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from ml import features
from ml.analysis import GROUP_COLUMNS  # age_band, booking_channel, distance_band
from ml.data import generate as gen

SEED = 42
BOOTSTRAP_ROUNDS = 1000
THRESHOLDS = np.round(np.arange(0.05, 0.951, 0.01), 2)
LEAKAGE_MARGIN = 0.03       # room for sampling luck on a finite pile (see the model report)
MAX_PLAUSIBLE_AUC = 0.90
SMALL_ROWS, SMALL_NO_SHOWS = 100, 20  # below either: "too small to judge"
BLANK = "(blank)"


class LeakageAlarm(Exception):
    """A score too good to be honest: stop and investigate before trusting any result."""


# ---------------------------------------------------------------- metrics
def ranking_metrics(y, p):
    """Threshold-free: how well the scores rank no-shows above attenders, and how honest the probabilities are."""
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
    }


def threshold_metrics(y, p, threshold):
    """Counts and rates when everyone with p >= threshold is flagged as a likely no-show."""
    y, flagged = np.asarray(y).astype(bool), np.asarray(p) >= threshold
    tp, fp = int((y & flagged).sum()), int((~y & flagged).sum())
    fn, tn = int((y & ~flagged).sum()), int((~y & ~flagged).sum())
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {
        "threshold": float(threshold),
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": recall,
        "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0,
        "balanced_accuracy": (recall + specificity) / 2,
        "accuracy": (tp + tn) / len(y),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def choose_threshold(y, p):
    """The threshold (0.05-0.95, step 0.01) with the best F1; on a tie the higher one (fewer false alarms)."""
    best, best_f1 = None, -1.0
    for threshold in THRESHOLDS:
        f1 = threshold_metrics(y, p, threshold)["f1"]
        if f1 >= best_f1:
            best, best_f1 = float(threshold), f1
    return best


def threshold_table(y, p, thresholds=(0.15, 0.20, 0.25, 0.30, 0.35, 0.40)):
    return [threshold_metrics(y, p, t) for t in thresholds]


# ---------------------------------------------------------------- leakage alarm and model choice
def check_leakage(auc, ceiling, where, model="model"):
    if auc > MAX_PLAUSIBLE_AUC:
        raise LeakageAlarm(f"{model}: ROC-AUC {auc:.3f} on {where} is above {MAX_PLAUSIBLE_AUC}; investigate leakage.")
    if auc > ceiling + LEAKAGE_MARGIN:
        raise LeakageAlarm(
            f"{model}: ROC-AUC {auc:.3f} on {where} beats the rule's own score ({ceiling:.3f}) by more than "
            f"{LEAKAGE_MARGIN}; investigate leakage."
        )


def select_model(boosting_minus_logistic):
    """Pass the (low, high) 95% interval of PR-AUC(gradient boosting) - PR-AUC(logistic regression)."""
    low, _high = boosting_minus_logistic
    return "gradient_boosting" if low > 0 else "logistic_regression"


# ---------------------------------------------------------------- bootstrap intervals
def _resamples(n, seed=SEED):
    return np.random.default_rng(seed).integers(0, n, size=(BOOTSTRAP_ROUNDS, n))


def paired_difference(y, p_a, p_b, metric=average_precision_score, seed=SEED):
    """metric(a) - metric(b) on the same rows, with a 95% interval from resampling those rows together."""
    y, p_a, p_b = np.asarray(y), np.asarray(p_a), np.asarray(p_b)
    diffs = []
    for idx in _resamples(len(y), seed):
        if 0 < y[idx].sum() < len(idx):
            diffs.append(metric(y[idx], p_a[idx]) - metric(y[idx], p_b[idx]))
    low, high = np.percentile(diffs, [2.5, 97.5])
    return {"diff": float(metric(y, p_a) - metric(y, p_b)), "low": float(low), "high": float(high)}


def _rate_with_interval(numerator, denominator):
    """Point value and 95% interval for a rate computed on each resample (rows: resamples)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        values = numerator / denominator
    point = values[0]
    rest = values[1:][~np.isnan(values[1:])]
    if np.isnan(point) or len(rest) == 0:
        return {"value": None, "low": None, "high": None}
    low, high = np.percentile(rest, [2.5, 97.5])
    return {"value": float(point), "low": float(low), "high": float(high)}


def _group_metrics(y, flagged, seed):
    """Recall, false-alarm rate and precision for one group, each with a bootstrap interval."""
    n = len(y)
    idx = np.vstack([np.arange(n), _resamples(n, seed)])  # row 0 = the real group, then the resamples
    yy, ff = y[idx], flagged[idx]
    tp, fp = (yy & ff).sum(axis=1), (~yy & ff).sum(axis=1)
    return {
        "recall": _rate_with_interval(tp, yy.sum(axis=1)),
        "false_alarm_rate": _rate_with_interval(fp, (~yy).sum(axis=1)),
        "precision": _rate_with_interval(tp, tp + fp),
    }


def group_table(pile, p, threshold, seed=SEED):
    """One row per value of each group column (blanks included), with sizes, rates and intervals."""
    y, flagged = pile["no_show"].to_numpy().astype(bool), np.asarray(p) >= threshold
    rows = []
    for column in GROUP_COLUMNS:
        labels = pile[column].astype(object).where(pile[column].notna(), BLANK).to_numpy()
        for value in [*gen.CATEGORIES[column], BLANK]:
            mask = labels == value
            if not mask.any():
                continue
            count, no_shows = int(mask.sum()), int(y[mask].sum())
            rows.append({
                "column": column, "value": value, "rows": count, "no_shows": no_shows,
                "small": count < SMALL_ROWS or no_shows < SMALL_NO_SHOWS,
                "actual_rate": no_shows / count,
                "mean_predicted": float(np.mean(np.asarray(p)[mask])),
                **_group_metrics(y[mask], flagged[mask], seed),
            })
    return rows


# ---------------------------------------------------------------- calibration and error analysis
def calibration_table(y, p, bands=10):
    """Rows sorted into 10 equal-size bands by predicted probability: predicted vs actual no-show rate."""
    frame = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)})
    frame["band"] = pd.qcut(frame["p"], bands, labels=False, duplicates="drop")
    grouped = frame.groupby("band")
    return [
        {"band": int(band) + 1, "rows": int(len(g)), "min_p": float(g["p"].min()), "max_p": float(g["p"].max()),
         "mean_predicted": float(g["p"].mean()), "actual_rate": float(g["y"].mean())}
        for band, g in grouped
    ]


def error_profile(pile, p, threshold):
    """How the four confusion-matrix boxes differ on a few telling inputs (validation pile)."""
    y, flagged = pile["no_show"].to_numpy().astype(bool), np.asarray(p) >= threshold
    boxes = {
        "caught no-shows (TP)": y & flagged,
        "missed no-shows (FN)": y & ~flagged,
        "false alarms (FP)": ~y & flagged,
        "correctly cleared (TN)": ~y & ~flagged,
    }
    profile = []
    for name, mask in boxes.items():
        part = pile[mask]
        profile.append({
            "box": name, "rows": int(mask.sum()),
            "mean_predicted": float(np.mean(np.asarray(p)[mask])) if mask.any() else None,
            "no_reminder": float((part["reminder_sent"] == "no").mean()) if mask.any() else None,
            "mean_lead_time": float(part["lead_time_days"].mean()) if mask.any() else None,
            "any_prior_no_show": float((part["prior_no_shows"].astype(float) > 0).mean()) if mask.any() else None,
            "phone_booking": float((part["booking_channel"] == "phone").mean()) if mask.any() else None,
        })
    return profile


def confident_mistakes(pile, p, threshold, top=10):
    """The most confident false alarms and misses, with their (fictional) inputs."""
    frame = pile[[features.ID, *features.FEATURES, features.TARGET]].copy()
    frame["p"] = np.asarray(p)
    false_alarms = frame[(frame["no_show"] == 0) & (frame["p"] >= threshold)].nlargest(top, "p")
    misses = frame[(frame["no_show"] == 1) & (frame["p"] < threshold)].nsmallest(top, "p")

    def records(part):
        out = []
        for _, row in part.iterrows():
            out.append({k: (None if pd.isna(v) else (v.item() if hasattr(v, "item") else v)) for k, v in row.items()})
        return out

    return {"false_alarms": records(false_alarms), "misses": records(misses)}
