"""
Week 3, phase 1: the synthetic appointment generator (ml/data/generate.py) and the committed dataset.

The data is invented by rules we wrote, so these tests check that the rules are applied the way the
data card says: reproducible with a seed, the documented columns and ranges, no column that leaks the
outcome, the documented missing values, about 20% no-shows, and a noise setting that really works.
"""
import json
import math

import pandas as pd
import pytest

from ml.data import generate as gen

FEATURES = [
    "lead_time_days", "weekday", "hour", "visit_type", "booking_channel",
    "reminder_sent", "prior_visits", "prior_no_shows", "distance_band", "age_band",
]


@pytest.fixture(scope="module")
def df():
    return gen.generate(seed=42, rows=6000, noise=1.0)


# ---------------------------------------------------------------- reproducibility
def test_same_seed_gives_identical_data():
    a = gen.generate(seed=7, rows=2000, noise=1.0)
    b = gen.generate(seed=7, rows=2000, noise=1.0)
    pd.testing.assert_frame_equal(a, b)


def test_different_seed_gives_different_data():
    a = gen.generate(seed=7, rows=2000, noise=1.0)
    b = gen.generate(seed=8, rows=2000, noise=1.0)
    assert not a.equals(b)


def test_noise_changes_only_the_outcome_not_the_features():
    """Same seed, different noise: identical appointments (blanks included); only no_show may differ."""
    low = gen.generate(seed=42, rows=3000, noise=0.5)
    high = gen.generate(seed=42, rows=3000, noise=2.0)
    pd.testing.assert_frame_equal(low.drop(columns="no_show"), high.drop(columns="no_show"))
    assert not low["no_show"].equals(high["no_show"])


# ---------------------------------------------------------------- schema and ranges
def test_exact_columns_in_documented_order(df):
    assert list(df.columns) == ["appointment_id", *FEATURES, "no_show"]
    assert len(df) == 6000


def test_ids_are_unique_and_sequential(df):
    assert df["appointment_id"].is_unique
    assert df["appointment_id"].iloc[0] == "A00001"
    assert df["appointment_id"].iloc[-1] == "A06000"


def test_numeric_ranges(df):
    assert df["lead_time_days"].between(0, 90).all()
    assert df["hour"].between(8, 17).all()
    visits = df["prior_visits"].dropna()
    assert visits.between(0, 20).all()
    assert df["prior_no_shows"].dropna().ge(0).all()


def test_prior_no_shows_never_exceed_prior_visits(df):
    both = df.dropna(subset=["prior_visits", "prior_no_shows"])
    assert (both["prior_no_shows"] <= both["prior_visits"]).all()


@pytest.mark.parametrize("column", list(gen.CATEGORIES))
def test_categories_use_only_documented_values(df, column):
    assert set(df[column].dropna().unique()) <= set(gen.CATEGORIES[column])


def test_outcome_is_binary_and_never_missing(df):
    assert df["no_show"].notna().all()
    assert set(df["no_show"].unique()) == {0, 1}


# ---------------------------------------------------------------- no leakage
def test_no_column_from_after_the_appointment_or_from_the_rule():
    """Only booking-time facts. Nothing known after the visit, and never the true probability."""
    columns = gen.generate(seed=1, rows=200, noise=1.0).columns
    banned = ("check", "arriv", "cancel", "attend", "prob", "logit", "risk", "score", "outcome")
    for column in columns:
        assert not any(word in column for word in banned), column


def test_no_feature_value_gives_away_the_outcome(df):
    """No category (with enough rows to judge) is all no-shows or all attended: no hidden copy of the label."""
    for column in FEATURES:
        rates = df.groupby(df[column].astype("string"), dropna=True)["no_show"].agg(["mean", "size"])
        rates = rates[rates["size"] >= 30]
        assert rates["mean"].between(0.01, 0.99).all(), column


# ---------------------------------------------------------------- missing values
@pytest.mark.parametrize(
    "column, low, high",
    [
        ("reminder_sent", 0.04, 0.08),
        ("prior_visits", 0.02, 0.045),
        ("distance_band", 0.06, 0.105),
        ("age_band", 0.025, 0.055),
    ],
)
def test_missing_rates_match_the_data_card(df, column, low, high):
    assert low <= df[column].isna().mean() <= high


def test_prior_counts_are_missing_together(df):
    assert (df["prior_visits"].isna() == df["prior_no_shows"].isna()).all()


def test_columns_without_blanks(df):
    for column in ["appointment_id", "lead_time_days", "weekday", "hour", "visit_type", "booking_channel"]:
        assert df[column].notna().all(), column


def test_distance_is_missing_more_often_for_phone_bookings(df):
    """Not missing at random: the data card says phone bookings skip the distance question more often."""
    missing = df["distance_band"].isna()
    phone = df["booking_channel"] == "phone"
    assert missing[phone].mean() > 2 * missing[~phone].mean()


# ---------------------------------------------------------------- outcome and noise
@pytest.mark.parametrize("noise", [0.5, 1.0, 2.0])
def test_about_twenty_percent_no_shows_at_any_noise(noise):
    rate = gen.generate(seed=42, rows=6000, noise=noise)["no_show"].mean()
    assert 0.17 <= rate <= 0.23


def test_more_noise_lowers_the_best_possible_score():
    scores = [gen.best_possible_roc_auc(seed=42, rows=6000, noise=n) for n in (0.0, 1.0, 3.0)]
    assert scores[0] > scores[1] > scores[2]
    assert all(0.5 < s < 1.0 for s in scores)


@pytest.mark.parametrize(
    "kwargs",
    [{"rows": 0}, {"rows": 99}, {"rows": 2.5}, {"noise": -0.1}, {"noise": math.nan}, {"noise": 6}, {"seed": -1}],
)
def test_bad_arguments_are_rejected(kwargs):
    args = {"seed": 42, "rows": 1000, "noise": 1.0, **kwargs}
    with pytest.raises(ValueError):
        gen.generate(**args)


# ---------------------------------------------------------------- the committed files
def test_committed_csv_is_exactly_what_the_generator_makes():
    """The CSV in git is reproducible: regenerate with the documented settings and compare checksums."""
    expected = gen.content_sha256_of_frame(gen.generate(seed=42, rows=6000, noise=1.0))
    assert gen.content_sha256_of_file(gen.DEFAULT_CSV) == expected


def test_committed_csv_loads_back_identically(df):
    pd.testing.assert_frame_equal(gen.load_csv(gen.DEFAULT_CSV), df)


def test_metadata_describes_the_committed_csv(df):
    meta = json.loads(gen.DEFAULT_META.read_text(encoding="utf-8"))
    assert meta["seed"] == 42 and meta["rows"] == 6000 and meta["noise"] == 1.0
    assert meta["content_sha256"] == gen.content_sha256_of_file(gen.DEFAULT_CSV)
    assert meta["no_show_rate"] == round(float(df["no_show"].mean()), 4)
    assert meta["columns"] == list(df.columns)
    assert meta["best_possible_roc_auc"] == round(gen.best_possible_roc_auc(42, 6000, 1.0), 4)


def test_crlf_line_endings_do_not_change_the_checksum(tmp_path, df):
    """git (core.autocrlf=true) may check the CSV out with Windows line endings; the checksum must not care."""
    text = df.to_csv(index=False, lineterminator="\n")
    lf, crlf = tmp_path / "lf.csv", tmp_path / "crlf.csv"
    lf.write_bytes(text.encode("utf-8"))
    crlf.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert gen.content_sha256_of_file(lf) == gen.content_sha256_of_file(crlf)
