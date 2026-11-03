"""
Seeded generator for the synthetic appointment dataset (see docs/ml/data-card.md).

Every row is an invented appointment described only by facts known when it is booked. Whether the
person misses it (no_show) comes from a rule WE wrote (EFFECTS below) plus random noise, so the data
shows nothing about real clinics or real people. The age-band, channel and other effects are arbitrary
choices made to give the later bias checks something to find; they are not claims about anyone.

Same seed + same settings = byte-identical CSV. Run from backend/:

    python -m ml.data.generate --seed 42 --rows 6000 --noise 1.0
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = DATA_DIR / "appointments.csv"
DEFAULT_META = DATA_DIR / "appointments.meta.json"

DEFAULT_SEED = 42
DEFAULT_ROWS = 6000
DEFAULT_NOISE = 1.0
MIN_ROWS, MAX_ROWS = 100, 1_000_000
MAX_NOISE = 5.0
TARGET_NO_SHOW_RATE = 0.20

# ---------------------------------------------------------------- how often each value is drawn
DISTRIBUTIONS = {
    "weekday": {"mon": 0.19, "tue": 0.18, "wed": 0.18, "thu": 0.18, "fri": 0.17, "sat": 0.10},
    "visit_type": {"new_visit": 0.20, "follow_up": 0.35, "routine_checkup": 0.30, "wellness_class": 0.15},
    "booking_channel": {"online": 0.55, "phone": 0.35, "in_person": 0.10},
    "age_band": {"18-24": 0.14, "25-34": 0.24, "35-44": 0.21, "45-54": 0.17, "55-64": 0.14, "65+": 0.10},
    "distance_band": {"under_5km": 0.35, "5_15km": 0.35, "15_30km": 0.20, "over_30km": 0.10},
}
CATEGORIES = {column: tuple(probs) for column, probs in DISTRIBUTIONS.items()}
CATEGORIES["reminder_sent"] = ("yes", "no")

REMINDER_RATE = {"online": 0.80, "phone": 0.60, "in_person": 0.55}  # chance a reminder was sent

# ---------------------------------------------------------------- the made-up rule behind no_show
# Each number is added to a "risk score" (log-odds). Values not listed add 0. All of them are
# arbitrary: they make the data behave in a way the models can learn, nothing more.
LEAD_TIME_PER_DAY, LEAD_TIME_CAP = 0.03, 60       # longer wait -> more risk, capped at 60 days
PRIOR_NO_SHOW_RATIO = 2.0                         # times prior_no_shows / (prior_visits + 1)
REMINDER_SENT = -0.8                              # a reminder lowers risk
EFFECTS = {
    "weekday": {"mon": 0.25, "fri": 0.30, "sat": 0.15},
    "hour": {8: 0.20, 16: 0.15, 17: 0.15},
    "visit_type": {"new_visit": 0.30, "routine_checkup": 0.10, "wellness_class": 0.40},
    "booking_channel": {"online": 0.20, "in_person": -0.30},
    "distance_band": {"5_15km": 0.15, "15_30km": 0.35, "over_30km": 0.60},
    "age_band": {"18-24": 0.45, "25-34": 0.30, "35-44": 0.10, "55-64": -0.10, "65+": 0.15},
}

# ---------------------------------------------------------------- blanks (decided after the outcome)
MISSING_RATE = {"reminder_sent": 0.06, "prior_counts": 0.03, "age_band": 0.04}
DISTANCE_MISSING_RATE = {"phone": 0.14, "other": 0.05}  # phone bookings skip the question more often

COLUMNS = [
    "appointment_id", "lead_time_days", "weekday", "hour", "visit_type", "booking_channel",
    "reminder_sent", "prior_visits", "prior_no_shows", "distance_band", "age_band", "no_show",
]
# One dtype per column, used both when generating and when loading the CSV back.
# "Int64" (capital I) is pandas' whole-number type that can also hold a blank.
DTYPES = {
    "appointment_id": "str", "lead_time_days": "int64", "weekday": "str", "hour": "int64",
    "visit_type": "str", "booking_channel": "str", "reminder_sent": "str", "prior_visits": "Int64",
    "prior_no_shows": "Int64", "distance_band": "str", "age_band": "str", "no_show": "int64",
}


def _check_args(seed, rows, noise):
    def is_int(value):
        return isinstance(value, (int, np.integer)) and not isinstance(value, bool)

    if not is_int(seed) or seed < 0:
        raise ValueError("seed must be a whole number >= 0.")
    if not is_int(rows) or not MIN_ROWS <= rows <= MAX_ROWS:
        raise ValueError(f"rows must be a whole number from {MIN_ROWS} to {MAX_ROWS}.")
    if isinstance(noise, bool) or not isinstance(noise, (int, float)) or not math.isfinite(noise) \
            or not 0 <= noise <= MAX_NOISE:
        raise ValueError(f"noise must be a number from 0 to {MAX_NOISE}.")


def _draw(rng, column, n):
    values, probs = zip(*DISTRIBUTIONS[column].items())
    return rng.choice(np.array(values, dtype=object), size=n, p=probs)


def _effect(column, values):
    return pd.Series(values).map(EFFECTS[column]).fillna(0.0).to_numpy(dtype=float)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _calibrate_intercept(score):
    """The constant that makes the average no-show chance TARGET_NO_SHOW_RATE (bisection, deterministic)."""
    low, high = -20.0, 20.0
    for _ in range(100):
        mid = (low + high) / 2
        if _sigmoid(mid + score).mean() < TARGET_NO_SHOW_RATE:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def simulate(seed=DEFAULT_SEED, rows=DEFAULT_ROWS, noise=DEFAULT_NOISE):
    """
    Return (frame, true_score). true_score is the rule's noise-free risk score per row: it is used only
    to measure the best possible ROC-AUC and is NEVER written to the CSV (that would leak the answer).

    The random draws always happen in the same order and the same number of times, whatever the noise,
    so changing the noise changes no_show only, never the appointments themselves.
    """
    _check_args(seed, rows, noise)
    rng = np.random.default_rng(seed)
    n = rows

    # 1. Booking-time facts. (Do not reorder these draws: it would change the dataset.)
    weekday = _draw(rng, "weekday", n)
    hour = rng.integers(8, 18, size=n)
    visit_type = _draw(rng, "visit_type", n)
    channel = _draw(rng, "booking_channel", n)
    lead_time = np.minimum(np.rint(rng.exponential(12.0, size=n)), 90).astype(np.int64)
    age_band = _draw(rng, "age_band", n)
    distance = _draw(rng, "distance_band", n)
    prior_visits = np.minimum(rng.poisson(3.0, size=n), 20)
    tendency = rng.beta(1.2, 8.0, size=n)  # hidden habit; only seen through the prior no-show count
    prior_no_shows = rng.binomial(prior_visits, tendency)
    reminder = np.where(rng.random(n) < pd.Series(channel).map(REMINDER_RATE).to_numpy(), "yes", "no")

    # 2. The outcome: rule score + noise, shifted so about 20% are no-shows, then a seeded coin flip.
    score = (
        LEAD_TIME_PER_DAY * np.minimum(lead_time, LEAD_TIME_CAP)
        + PRIOR_NO_SHOW_RATIO * prior_no_shows / (prior_visits + 1)
        + np.where(reminder == "yes", REMINDER_SENT, 0.0)
        + _effect("weekday", weekday)
        + _effect("hour", hour)
        + _effect("visit_type", visit_type)
        + _effect("booking_channel", channel)
        + _effect("distance_band", distance)
        + _effect("age_band", age_band)
    )
    noisy_score = score + noise * rng.standard_normal(n)
    intercept = _calibrate_intercept(noisy_score)
    no_show = (rng.random(n) < _sigmoid(intercept + noisy_score)).astype(np.int64)

    # 3. Blanks, drawn after the outcome so they never depend on it.
    no_reminder_info = rng.random(n) < MISSING_RATE["reminder_sent"]
    no_prior_counts = rng.random(n) < MISSING_RATE["prior_counts"]
    no_age = rng.random(n) < MISSING_RATE["age_band"]
    distance_rate = np.where(channel == "phone", DISTANCE_MISSING_RATE["phone"], DISTANCE_MISSING_RATE["other"])
    no_distance = rng.random(n) < distance_rate

    width = max(5, len(str(n)))
    frame = pd.DataFrame({
        "appointment_id": [f"A{i:0{width}d}" for i in range(1, n + 1)],
        "lead_time_days": lead_time,
        "weekday": weekday,
        "hour": hour,
        "visit_type": visit_type,
        "booking_channel": channel,
        "reminder_sent": pd.Series(reminder).mask(no_reminder_info),
        "prior_visits": pd.Series(prior_visits).astype("Int64").mask(no_prior_counts),
        "prior_no_shows": pd.Series(prior_no_shows).astype("Int64").mask(no_prior_counts),
        "distance_band": pd.Series(distance).mask(no_distance),
        "age_band": pd.Series(age_band).mask(no_age),
        "no_show": no_show,
    })
    return frame.astype(DTYPES)[COLUMNS], intercept + score


def generate(seed=DEFAULT_SEED, rows=DEFAULT_ROWS, noise=DEFAULT_NOISE):
    """The dataset only (what goes into the CSV)."""
    return simulate(seed, rows, noise)[0]


def best_possible_roc_auc(seed=DEFAULT_SEED, rows=DEFAULT_ROWS, noise=DEFAULT_NOISE):
    """
    ROC-AUC of the rule itself (noise-free score) on this data: a ceiling no model can honestly beat,
    because the noise and the final coin flip cannot be predicted from the columns.
    """
    frame, true_score = simulate(seed, rows, noise)
    return float(roc_auc_score(frame["no_show"], true_score))


# ---------------------------------------------------------------- files and checksums
def csv_text(frame):
    return frame.to_csv(index=False, lineterminator="\n")


def content_sha256_of_frame(frame):
    return hashlib.sha256(csv_text(frame).encode("utf-8")).hexdigest()


def content_sha256_of_file(path):
    """SHA-256 of the CSV text with line endings normalised, so a CRLF checkout (git autocrlf) still matches."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_csv(path=DEFAULT_CSV):
    # Only empty cells are blanks; strings such as "NA" would stay text (none are used).
    return pd.read_csv(path, dtype=DTYPES, keep_default_na=False, na_values=[""])[COLUMNS]


def write(seed=DEFAULT_SEED, rows=DEFAULT_ROWS, noise=DEFAULT_NOISE, csv_path=DEFAULT_CSV, meta_path=DEFAULT_META):
    frame, true_score = simulate(seed, rows, noise)
    text = csv_text(frame)
    Path(csv_path).write_bytes(text.encode("utf-8"))
    meta = {
        "description": "Synthetic appointment no-show dataset. Invented by a seeded script; no real people.",
        "generator": "ml.data.generate",
        "command": f"python -m ml.data.generate --seed {seed} --rows {rows} --noise {float(noise)}",
        "seed": seed,
        "rows": rows,
        "noise": float(noise),
        "columns": COLUMNS,
        "no_show_rate": round(float(frame["no_show"].mean()), 4),
        "missing_rate": {c: round(float(frame[c].isna().mean()), 4) for c in COLUMNS if frame[c].isna().any()},
        "best_possible_roc_auc": round(float(roc_auc_score(frame["no_show"], true_score)), 4),
        "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "content_sha256_note": "SHA-256 of the CSV text with line endings normalised to \\n.",
    }
    Path(meta_path).write_bytes((json.dumps(meta, indent=2) + "\n").encode("utf-8"))
    return meta


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate the synthetic appointment dataset.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--noise", type=float, default=DEFAULT_NOISE,
                        help=f"extra randomness in the outcome, 0 to {MAX_NOISE} (default {DEFAULT_NOISE})")
    parser.add_argument("--out", type=Path, default=DEFAULT_CSV, help="CSV path; metadata goes next to it")
    args = parser.parse_args(argv)
    try:
        meta = write(args.seed, args.rows, args.noise, args.out, args.out.with_suffix(".meta.json"))
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Wrote {args.out} ({meta['rows']} rows, no-show rate {meta['no_show_rate']:.1%}, "
          f"best possible ROC-AUC {meta['best_possible_roc_auc']})")


if __name__ == "__main__":
    main()
