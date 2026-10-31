"""
Exploratory analysis of the TRAINING pile only, written as Markdown tables to docs/ml/eda.md.

Validation and test rows contribute only their size, no-show rate and group counts (so we know how
noisy later per-group metrics will be); nothing else about them is looked at, so no modelling choice
can be shaped by the rows that will judge the models. Run from backend/:

    python -m ml.analysis
"""
from pathlib import Path

import pandas as pd

from ml import features
from ml.data import generate as gen

REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "ml" / "eda.md"
GROUP_COLUMNS = ["age_band", "booking_channel", "distance_band"]  # the per-group checks in phases 3 and 7
BLANK = "(blank)"
LEAD_TIME_BANDS = ([-1, 0, 7, 14, 30, 60, 90], ["0 (same day)", "1-7", "8-14", "15-30", "31-60", "61-90"])


# ---------------------------------------------------------------- formatting helpers
def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def _pct(value):
    return f"{value:.1%}"


def _n(value):
    return f"{value:,}"


def _rate_rows(labels, outcome):
    """Rows of (value, rows, no-shows, rate), in the category order of `labels` (a categorical Series)."""
    stats = outcome.groupby(labels, observed=True).agg(["size", "sum", "mean"])
    return [[value, _n(int(r["size"])), _n(int(r["sum"])), _pct(r["mean"])] for value, r in stats.iterrows()]


def _ordered(column, values):
    """Documented order for categories (so tables read naturally), blanks last."""
    order = [str(v) for v in gen.CATEGORIES.get(column, sorted(values.dropna().unique()))]
    return pd.Categorical(values.astype(object).where(values.notna(), BLANK).map(str), categories=order + [BLANK])


# ---------------------------------------------------------------- sections
def _split_section(split, total):
    rows = []
    for name, pile in (("train", split.train), ("validation", split.validation), ("test", split.test)):
        rows.append([name, _n(len(pile)), _pct(len(pile) / total), _n(int(pile["no_show"].sum())),
                     _pct(pile["no_show"].mean())])
    return _table(["Pile", "Rows", "Share", "No-shows", "No-show rate"], rows)


def _group_size_section(split):
    parts = []
    for column in GROUP_COLUMNS:
        counts = {
            name: pd.Series(_ordered(column, pile[column])).value_counts(sort=False)
            for name, pile in (("train", split.train), ("validation", split.validation), ("test", split.test))
        }
        rows = [[value, *(_n(int(counts[name][value])) for name in counts)] for value in counts["train"].index
                if any(counts[name][value] for name in counts)]
        parts.append(f"**{column}**\n\n" + _table(["Value", "Train", "Validation", "Test"], rows))
    return "\n\n".join(parts)


def _columns_section(train):
    rows = []
    for column in features.FEATURES:
        kind = "number" if column in features.NUMERIC else "category"
        blanks = int(train[column].isna().sum())
        rows.append([f"`{column}`", kind, _n(blanks), _pct(blanks / len(train)), train[column].nunique()])
    return _table(["Column", "Treated as", "Blanks", "Blank %", "Distinct values"], rows)


def _missing_section(train):
    rows = []
    for column in features.FEATURES:
        blank = train[column].isna()
        if not blank.any():
            continue
        rows.append([f"`{column}`", _n(int(blank.sum())), _pct(train.loc[blank, "no_show"].mean()),
                     _pct(train.loc[~blank, "no_show"].mean())])
    by_channel = [
        [channel, _n(int((train["booking_channel"] == channel).sum())),
         _pct(train.loc[train["booking_channel"] == channel, "distance_band"].isna().mean())]
        for channel in gen.CATEGORIES["booking_channel"]
    ]
    return (
        _table(["Column", "Blank rows", "No-show rate when blank", "No-show rate when filled"], rows)
        + "\n\nDistance blanks by booking channel:\n\n"
        + _table(["Booking channel", "Rows", "Distance blank"], by_channel)
    )


def _numbers_section(train):
    described = train[features.NUMERIC].astype(float).describe()
    stats = ["count", "mean", "std", "min", "25%", "50%", "75%", "max"]
    rows = [[f"`{c}`", *(f"{described.loc[s, c]:.2f}" if s != "count" else _n(int(described.loc[s, c]))
                         for s in stats)] for c in features.NUMERIC]
    bins, labels = LEAD_TIME_BANDS
    lead = pd.cut(train["lead_time_days"], bins=bins, labels=labels)
    prior = train["prior_no_shows"].astype(float)
    prior_band = pd.Series(
        pd.Categorical(prior.map(lambda v: BLANK if pd.isna(v) else ("3+" if v >= 3 else str(int(v)))),
                       categories=["0", "1", "2", "3+", BLANK]),
        index=train.index,
    )
    return (
        _table(["Column", "Non-blank", "Mean", "Std", "Min", "25%", "Median", "75%", "Max"], rows)
        + "\n\nNo-show rate by lead time (days):\n\n"
        + _table(["Lead time", "Rows", "No-shows", "No-show rate"], _rate_rows(lead, train["no_show"]))
        + "\n\nNo-show rate by earlier no-shows:\n\n"
        + _table(["Earlier no-shows", "Rows", "No-shows", "No-show rate"], _rate_rows(prior_band, train["no_show"]))
    )


def _categories_section(train):
    parts = []
    for column in features.CATEGORICAL:
        labels = pd.Series(_ordered(column, train[column]), index=train.index)
        rows = _rate_rows(labels, train["no_show"])
        parts.append(f"**{column}**\n\n" + _table(["Value", "Rows", "No-shows", "No-show rate"], rows))
    return "\n\n".join(parts)


def render(frame):
    split = features.split_data(frame)
    train = split.train
    rate = train["no_show"].mean()
    distance_blank = train["distance_band"].isna()
    phone = train["booking_channel"] == "phone"
    return f"""# Exploratory analysis (training pile only)

> Generated by `python -m ml.analysis` from `backend/ml/data/appointments.csv`. Do not edit by hand: the test
> suite checks that this file matches the script. The data is **synthetic** (see the [data card](data-card.md)).

Rows analysed: **{_n(len(train))}** (training pile only)

The data is split **before** anything is learned. Every table from section 3 on uses the training pile only.
The validation and test piles appear only as sizes, no-show rates and group counts (sections 1 and 2), so
no choice about the model can be shaped by the rows that will later judge it.

## 1. The split

70 / 15 / 15, stratified on `no_show` (each pile keeps the same no-show rate), seed {features.SPLIT_SEED}.
Only the labels decide where a row goes, so no feature value can influence the split.

{_split_section(split, len(frame))}

## 2. Group sizes per pile

These are the groups checked for bias in phases 3 and 7. Small counts in the validation and test piles mean
noisy per-group metrics, so every per-group metric will be reported next to its group size.

{_group_size_section(split)}

## 3. Columns

`appointment_id` (a row label) and `no_show` (the answer) are not inputs. The model sees these ten columns:

{_columns_section(train)}

## 4. Class balance

{_table(["Outcome", "Rows", "Share"], [["attended (0)", _n(int((train["no_show"] == 0).sum())), _pct(1 - rate)],
                                     ["no-show (1)", _n(int(train["no_show"].sum())), _pct(rate)]])}

A model that always says "will attend" would be right {_pct(1 - rate)} of the time and would never find a
single no-show. That is why phase 3 judges models by PR-AUC, recall, precision, F1 and balanced accuracy,
not by accuracy.

## 5. Missing values

{_missing_section(train)}

* Blanks were added at random except for distance: phone bookings leave it blank
  {_pct(distance_blank[phone].mean())} of the time vs {_pct(distance_blank[~phone].mean())} for other channels.
  So "distance is blank" partly means "booked by phone".
* For the columns blanked completely at random, any gap between "when blank" and "when filled" is chance:
  the blanks were added after the outcome and never looked at it. Small groups wobble.
* Numbers (`prior_visits`, `prior_no_shows`) are filled with the **training median** and get a "was blank"
  column; categories get a new value, `missing`. Both steps live inside the pipeline and are fitted on the
  training pile only.
* Blank rows are kept, not deleted: dropping them would throw away {_pct(train[features.FEATURES].isna().any(axis=1).mean())}
  of the training rows and would drop phone bookings more than others.

## 6. Numbers

{_numbers_section(train)}

All three numbers are skewed (many small values, a few large ones), so blanks are filled with the median,
which a few large values cannot drag upwards, rather than the mean. Numbers are scaled so that logistic
regression treats them fairly; tree models ignore the scaling.

## 7. Categories

{_categories_section(train)}

`hour` is treated as a category rather than a number: the early and late slots differ from midday in a way a
single straight line cannot capture.

## 8. Leakage checklist

* [x] Split first, stratified, seeded; the split depends only on the labels.
* [x] Fill-in values and scaling are learned inside the pipeline from the training pile only (tested).
* [x] This analysis reads only the training pile, apart from sizes, rates and group counts (tested).
* [x] No input is derived from the outcome; the dataset has no post-visit columns (phase 1 tests).
* [x] `appointment_id` is never an input.
* [ ] The test pile is used once, at the end of phase 3 (not used yet).
"""


def main():
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_bytes(render(gen.load_csv()).encode("utf-8"))
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
