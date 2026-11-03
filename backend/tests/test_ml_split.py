"""
Week 3, phase 2: the train / validation / test split, the preprocessing and the analysis report.

The rule these tests protect: split FIRST, then learn anything (fill-in values, scaling, the analysis)
from the training pile only, so the validation and test piles stay unseen until they are used.
"""
import numpy as np
import pandas as pd
import pytest

from ml import analysis, features
from ml.data import generate as gen


@pytest.fixture(scope="module")
def frame():
    return gen.load_csv()


@pytest.fixture(scope="module")
def split(frame):
    return features.split_data(frame)


def fitted(train):
    return features.build_preprocessor().fit(features.features_of(train))


# ---------------------------------------------------------------- the split
def test_split_sizes_are_70_15_15(split):
    assert (len(split.train), len(split.validation), len(split.test)) == (4200, 900, 900)


def test_piles_do_not_overlap_and_cover_every_row(frame, split):
    ids = [set(pile["appointment_id"]) for pile in (split.train, split.validation, split.test)]
    assert not ids[0] & ids[1] and not ids[0] & ids[2] and not ids[1] & ids[2]
    assert ids[0] | ids[1] | ids[2] == set(frame["appointment_id"])


def test_every_pile_keeps_the_overall_no_show_rate(frame, split):
    overall = frame["no_show"].mean()
    for pile in (split.train, split.validation, split.test):
        assert abs(pile["no_show"].mean() - overall) <= 0.01


def test_split_is_reproducible_and_depends_on_the_seed(frame, split):
    again = features.split_data(frame)
    assert list(again.test["appointment_id"]) == list(split.test["appointment_id"])
    other = features.split_data(frame, seed=7)
    assert list(other.test["appointment_id"]) != list(split.test["appointment_id"])


def test_inputs_are_exactly_the_documented_features(split):
    inputs = features.features_of(split.train)
    assert list(inputs.columns) == features.FEATURES
    assert "appointment_id" not in inputs.columns and "no_show" not in inputs.columns
    assert features.FEATURES == [c for c in gen.COLUMNS if c not in ("appointment_id", "no_show")]
    assert sorted(features.NUMERIC + features.CATEGORICAL) == sorted(features.FEATURES)
    assert list(features.target_of(split.train)) == list(split.train["no_show"])


# ---------------------------------------------------------------- training-only preprocessing
def test_fill_in_and_scaling_values_come_from_the_training_pile(split):
    pre = fitted(split.train)
    numeric = pre.named_transformers_["num"]
    medians = split.train[features.NUMERIC].astype(float).median()
    np.testing.assert_allclose(numeric.named_steps["impute"].statistics_, medians.to_numpy())

    filled = split.train[features.NUMERIC].astype(float).fillna(medians)
    scaler = numeric.named_steps["scale"]
    np.testing.assert_allclose(scaler.mean_[:3], filled.mean().to_numpy())
    np.testing.assert_allclose(scaler.scale_[:3], filled.std(ddof=0).to_numpy())


def test_changing_validation_and_test_rows_changes_nothing_learned(frame, split):
    """Wildly edit every validation and test row: the split and everything fitted stay identical."""
    held_out = split.validation.index.union(split.test.index)
    edited = frame.copy()
    edited.loc[held_out, "lead_time_days"] = 90
    edited.loc[held_out, ["prior_visits", "prior_no_shows"]] = pd.NA
    edited.loc[held_out, "visit_type"] = "wellness_class"
    edited.loc[held_out, "age_band"] = np.nan

    again = features.split_data(edited)
    pd.testing.assert_frame_equal(again.train, split.train)

    original, retrained = fitted(split.train), fitted(again.train)
    X = features.features_of(split.train)
    np.testing.assert_array_equal(original.transform(X), retrained.transform(X))


def test_rows_with_every_optional_field_blank_are_filled(split):
    pre = fitted(split.train)
    row = pd.DataFrame([{
        "lead_time_days": 5, "weekday": "mon", "hour": 9, "visit_type": "follow_up",
        "booking_channel": "phone", "reminder_sent": np.nan, "prior_visits": pd.NA,
        "prior_no_shows": pd.NA, "distance_band": np.nan, "age_band": np.nan,
    }]).astype({c: gen.DTYPES[c] for c in features.FEATURES})
    out = pre.transform(row)
    assert not np.isnan(out).any()

    names = list(pre.get_feature_names_out())
    values = dict(zip(names, out[0]))
    for name in ["cat__reminder_sent_missing", "cat__distance_band_missing", "cat__age_band_missing"]:
        assert values[name] == 1.0, name
    assert any("missingindicator_prior_visits" in n for n in names)


def test_hour_is_treated_as_a_category(split):
    names = list(fitted(split.train).get_feature_names_out())
    assert {f"cat__hour_{h}" for h in range(8, 18)} <= set(names)


def test_an_unseen_category_does_not_crash(split):
    pre = fitted(split.train)
    row = features.features_of(split.train).iloc[[0]].copy()
    row["weekday"] = "sun"
    out = pre.transform(row)
    names = list(pre.get_feature_names_out())
    weekday_columns = [i for i, n in enumerate(names) if n.startswith("cat__weekday_")]
    assert out[0, weekday_columns].sum() == 0


# ---------------------------------------------------------------- the analysis report
def test_committed_report_is_what_the_script_produces(frame):
    committed = analysis.REPORT_PATH.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    assert committed == analysis.render(frame)


def test_report_says_it_analysed_the_training_pile_only(frame):
    assert "Rows analysed: **4,200** (training pile only)" in analysis.render(frame)


def test_report_ignores_the_contents_of_validation_and_test_rows(frame, split):
    """Only their size, no-show rate and group counts are reported; editing anything else changes nothing."""
    held_out = split.validation.index.union(split.test.index)
    edited = frame.copy()
    edited.loc[held_out, "lead_time_days"] = 0
    edited.loc[held_out, ["prior_visits", "prior_no_shows"]] = pd.NA
    edited.loc[held_out, ["weekday", "visit_type", "reminder_sent"]] = ["sat", "new_visit", np.nan]
    assert analysis.render(edited) == analysis.render(frame)
