"""
Reproducible training script: rebuilds the model artifact from the committed dataset.

It runs the SAME phase 3 experiment code (tuning, model choice, threshold), then saves the chosen fitted
Pipeline and its metadata. Fixed seeds and pinned packages make it reproducible. Run from backend/:

    python -m ml.train           # write ml/artifacts/noshow-1.0.0.joblib + .json
    python -m ml.train --check   # rebuild in memory and compare with the committed files; writes nothing

"Reproduces" means the same predictions (to 1e-12) and the same yes/no labels on all 6,000 rows, and
identical metadata. Identical file bytes are reported too, but not required: a pickle can store the same
model in different bytes on another platform.
"""
import argparse
import json
import sys

import numpy as np

from ml import artifact, experiment, features
from ml.data import generate as gen

TOLERANCE = 1e-12


class DatasetChanged(Exception):
    """The CSV no longer matches its recorded checksum: retraining would not reproduce the artifact."""


def build():
    """Train from scratch. Returns (pipeline, metadata, model file bytes); writes nothing."""
    data_meta = json.loads(gen.DEFAULT_META.read_text(encoding="utf-8"))
    if gen.content_sha256_of_file(gen.DEFAULT_CSV) != data_meta["content_sha256"]:
        raise DatasetChanged("appointments.csv does not match its recorded checksum; regenerate it first.")
    results, fitted = experiment.fit_and_evaluate(gen.load_csv())
    pipeline = fitted[results["chosen"]]
    data = artifact.model_bytes(pipeline)
    return pipeline, artifact.build_metadata(results, artifact.sha256_bytes(data)), data


def check(built):
    """Compare a freshly built (pipeline, metadata, bytes) with the committed, checksum-verified artifact."""
    pipeline, metadata, data = built
    committed, committed_metadata = artifact.load_verified()
    X = features.features_of(gen.load_csv())
    p_new, p_old = pipeline.predict_proba(X)[:, 1], committed.predict_proba(X)[:, 1]
    threshold = committed_metadata["threshold"]
    max_difference = float(np.max(np.abs(p_new - p_old)))
    same_labels = bool(((p_new >= threshold) == (p_old >= threshold)).all())

    def without_checksum(m):
        return {k: v for k, v in m.items() if k != "model_sha256"}

    report = {
        "predictions_identical": max_difference <= TOLERANCE and same_labels,
        "max_probability_difference": max_difference,
        "labels_identical": same_labels,
        "metadata_identical": without_checksum(metadata) == without_checksum(committed_metadata),
        "bytes_identical": artifact.sha256_bytes(data) == committed_metadata["model_sha256"],
        "rebuilt_sha256": artifact.sha256_bytes(data),
        "committed_sha256": committed_metadata["model_sha256"],
    }
    report["ok"] = report["predictions_identical"] and report["metadata_identical"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Train (or check) the no-show demo model artifact.")
    parser.add_argument("--check", action="store_true", help="rebuild in memory and compare; write nothing")
    args = parser.parse_args(argv)

    if args.check:
        report = check(build())
        for key, value in report.items():
            print(f"{key}: {value}")
        print("OK: the committed artifact is reproduced." if report["ok"] else "FAILED: the rebuild differs.")
        return 0 if report["ok"] else 1

    _, metadata, data = build()
    artifact.save(data, metadata)
    digest = metadata["model_sha256"]
    print(f"Wrote {artifact.MODEL_PATH} and {artifact.METADATA_PATH}")
    print(f"SHA-256: {digest}")
    if digest != artifact.EXPECTED_SHA256:
        print("The checksum changed. Review the new model, then set EXPECTED_SHA256 in ml/artifact.py to the value above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
