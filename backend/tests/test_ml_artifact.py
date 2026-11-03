"""
Week 3, phase 4: the saved pipeline artifact, its metadata, the SHA-256 check before loading, and the
reproducible training script.

A .joblib file is a pickle: loading it can run code hidden inside. So the loader must refuse any file
whose bytes do not match the checksum committed in the code, BEFORE unpickling anything.
The reproduction tests retrain from scratch (about 40 s); set ML_SKIP_SLOW=1 to skip them locally.
"""
import json
import os
import shutil
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pytest
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from ml import artifact, experiment, features, train
from ml.data import generate as gen

slow = pytest.mark.skipif(os.environ.get("ML_SKIP_SLOW") == "1", reason="ML_SKIP_SLOW=1 set")
ML_PACKAGES = ["scikit-learn", "numpy", "pandas", "joblib", "scipy"]


@pytest.fixture(scope="module")
def loaded():
    return artifact.load_verified()


@pytest.fixture(scope="module")
def built():
    return train.build()


@pytest.fixture
def copies(tmp_path):
    """Copies of the committed model and metadata that a test may damage."""
    model = tmp_path / artifact.MODEL_PATH.name
    meta = tmp_path / artifact.METADATA_PATH.name
    shutil.copyfile(artifact.MODEL_PATH, model)
    shutil.copyfile(artifact.METADATA_PATH, meta)
    return model, meta


# ---------------------------------------------------------------- the committed files
def test_committed_file_matches_the_checksum_in_code_and_metadata():
    digest = artifact.sha256_bytes(artifact.MODEL_PATH.read_bytes())
    metadata = json.loads(artifact.METADATA_PATH.read_text(encoding="utf-8"))
    assert digest == artifact.EXPECTED_SHA256 == metadata["model_sha256"]
    assert len(artifact.EXPECTED_SHA256) == 64


def test_artifact_is_one_pipeline_with_preprocessing_and_model(loaded):
    pipeline, _ = loaded
    assert isinstance(pipeline, Pipeline)
    assert isinstance(pipeline.named_steps["preprocess"], ColumnTransformer)
    assert isinstance(pipeline.named_steps["model"], LogisticRegression)


def test_artifact_takes_raw_rows_and_returns_probabilities(loaded):
    pipeline, _ = loaded
    p = pipeline.predict_proba(features.features_of(gen.load_csv().head(50)))[:, 1]
    assert ((p > 0) & (p < 1)).all()


# ---------------------------------------------------------------- refusing to load
def test_tampered_file_is_refused_before_unpickling(copies, monkeypatch):
    model, meta = copies
    data = bytearray(model.read_bytes())
    data[len(data) // 2] ^= 0xFF  # flip one byte in the middle
    model.write_bytes(bytes(data))

    def trap(*args, **kwargs):
        raise AssertionError("joblib.load must not run on a file that failed the checksum")

    monkeypatch.setattr(artifact.joblib, "load", trap)
    with pytest.raises(artifact.ArtifactIntegrityError):
        artifact.load_verified(model, meta)


def test_metadata_with_a_different_checksum_is_refused(copies):
    model, meta = copies
    metadata = json.loads(meta.read_text(encoding="utf-8"))
    metadata["model_sha256"] = "0" * 64
    meta.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(artifact.ArtifactIntegrityError):
        artifact.load_verified(model, meta)


def test_missing_file_is_reported_as_unavailable(tmp_path):
    with pytest.raises(artifact.ArtifactUnavailable):
        artifact.load_verified(tmp_path / "missing.joblib", tmp_path / "missing.json")


def test_a_different_scikit_learn_version_is_refused(copies):
    model, meta = copies
    metadata = json.loads(meta.read_text(encoding="utf-8"))
    metadata["environment"]["scikit-learn"] = "0.0.1"
    meta.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(artifact.ArtifactIncompatible):
        artifact.load_verified(model, meta)


# ---------------------------------------------------------------- the metadata
def test_metadata_describes_the_model_honestly(loaded):
    _, metadata = loaded
    metrics = json.loads(experiment.METRICS_PATH.read_text(encoding="utf-8"))
    chosen = metrics["chosen"]
    data_meta = json.loads(gen.DEFAULT_META.read_text(encoding="utf-8"))

    assert metadata["model_version"] == "noshow-1.0.0" == artifact.MODEL_VERSION
    assert metadata["model"]["type"] == chosen and metadata["model"]["fitted_on"] == "train"
    assert metadata["threshold"] == metrics["validation"][chosen]["threshold"]
    assert metadata["labels"] == {"1": "likely_no_show", "0": "likely_attend"}
    assert metadata["training_data"]["content_sha256"] == data_meta["content_sha256"]
    assert metadata["metrics"]["test"] == metrics["test"][chosen]
    assert metadata["metrics"]["validation"] == metrics["validation"][chosen]
    assert "not medical advice" in metadata["notice"].lower()
    for package in ML_PACKAGES:
        assert metadata["environment"][package] == version(package)


def test_input_schema_matches_the_features_and_the_data_card(loaded):
    _, metadata = loaded
    schema = {field["name"]: field for field in metadata["input_schema"]}
    assert list(schema) == features.FEATURES
    for name, values in gen.CATEGORIES.items():
        assert schema[name]["type"] == "category" and schema[name]["allowed"] == list(values)
    assert (schema["lead_time_days"]["min"], schema["lead_time_days"]["max"]) == (0, 90)
    assert (schema["hour"]["min"], schema["hour"]["max"]) == (8, 17)
    assert (schema["prior_visits"]["min"], schema["prior_visits"]["max"]) == (0, 20)
    blank_ok = {name for name, field in schema.items() if field["may_be_blank"]}
    assert blank_ok == {"reminder_sent", "prior_visits", "prior_no_shows", "distance_band", "age_band"}


# ---------------------------------------------------------------- reproducibility
def test_ml_packages_are_pinned_and_installed_at_the_pinned_version():
    lines = Path(__file__).resolve().parents[1].joinpath("requirements.txt").read_text(encoding="utf-8-sig").splitlines()
    pins = dict(line.split("==") for line in lines if "==" in line)
    for package in ML_PACKAGES:
        assert pins[package] == version(package), package


@slow
def test_retraining_reproduces_the_same_predictions_and_metadata(built, loaded):
    rebuilt, rebuilt_metadata, _ = built
    committed, committed_metadata = loaded
    X = features.features_of(gen.load_csv())
    p_new, p_old = rebuilt.predict_proba(X)[:, 1], committed.predict_proba(X)[:, 1]
    np.testing.assert_allclose(p_new, p_old, rtol=0, atol=1e-12)
    threshold = committed_metadata["threshold"]
    assert ((p_new >= threshold) == (p_old >= threshold)).all()
    ignore = {"model_sha256"}  # bytes may legitimately differ across platforms; predictions may not
    assert {k: v for k, v in rebuilt_metadata.items() if k not in ignore} == \
           {k: v for k, v in committed_metadata.items() if k not in ignore}


@slow
def test_check_mode_passes_on_the_committed_files(built):
    report = train.check(built)
    assert report["predictions_identical"] and report["metadata_identical"]
    assert report["ok"]


def test_check_mode_fails_when_predictions_differ(loaded):
    """Feed check() a 'rebuilt' model that answers differently: it must report a failure."""
    pipeline, metadata = loaded
    other = Pipeline(pipeline.steps[:-1] + [("model", LogisticRegression(C=100.0, max_iter=2000))])
    frame = gen.load_csv()
    other.fit(features.features_of(frame), features.target_of(frame))
    report = train.check((other, metadata, b"different bytes"))
    assert not report["predictions_identical"] and not report["ok"]
