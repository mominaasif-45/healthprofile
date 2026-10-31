"""
The model's inputs, the train / validation / test split and the preprocessing (see docs/ml/eda.md).

One place for these so training (phases 3-4) and the API (phase 5) can never disagree about columns.
Order of work: split FIRST, then fit build_preprocessor() on the training pile only. Its fill-in values
and scaling are learned inside the pipeline, so validation and test rows never influence them.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

ID = "appointment_id"  # a row label only, never an input
TARGET = "no_show"
FEATURES = [
    "lead_time_days", "weekday", "hour", "visit_type", "booking_channel",
    "reminder_sent", "prior_visits", "prior_no_shows", "distance_band", "age_band",
]
NUMERIC = ["lead_time_days", "prior_visits", "prior_no_shows"]
# hour is a category: 8:00 and 16:00-17:00 behave differently from midday, which one straight line can't show.
CATEGORICAL = ["weekday", "hour", "visit_type", "booking_channel", "reminder_sent", "distance_band", "age_band"]
MISSING = "missing"  # the value a blank category becomes

SPLIT_SEED = 42
VALIDATION_SHARE = TEST_SHARE = 0.15  # the rest (70%) is the training pile


@dataclass(frozen=True)
class Split:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def split_data(frame, seed=SPLIT_SEED):
    """
    70 / 15 / 15, stratified on no_show so every pile keeps the same no-show rate. Only the labels
    decide which pile a row lands in, so no feature value can influence the split.
    """
    held_out = VALIDATION_SHARE + TEST_SHARE
    train, rest = train_test_split(frame, test_size=held_out, stratify=frame[TARGET], random_state=seed)
    validation, test = train_test_split(
        rest, test_size=TEST_SHARE / held_out, stratify=rest[TARGET], random_state=seed
    )
    return Split(train, validation, test)


def features_of(frame):
    return frame[FEATURES]


def target_of(frame):
    return frame[TARGET]


def as_float(frame):
    """Whole numbers that may be blank (pandas Int64) -> plain floats with NaN blanks."""
    return pd.DataFrame(frame).astype("float64")


def as_text(frame):
    """Categories as plain text with NaN blanks (hour 8 -> "8"), so every column holds one kind of value."""
    return pd.DataFrame(frame).apply(lambda col: col.map(lambda v: np.nan if pd.isna(v) else str(v))).astype(object)


def build_preprocessor():
    """Unfitted. Numbers: training median for blanks + a 'was blank' column + scaling. Categories: blank -> 'missing' + one-hot."""
    numeric = Pipeline([
        ("to_float", FunctionTransformer(as_float, feature_names_out="one-to-one")),
        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("to_text", FunctionTransformer(as_text, feature_names_out="one-to-one")),
        ("impute", SimpleImputer(strategy="constant", fill_value=MISSING)),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer([("num", numeric, NUMERIC), ("cat", categorical, CATEGORICAL)])
