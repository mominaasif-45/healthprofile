"""
The saved model: one fitted scikit-learn Pipeline (preprocessing + model) in a .joblib file, plus a JSON
metadata file that describes it.

SECURITY: a .joblib file is a pickle, and unpickling can run any code hidden inside the file. So:
* we only ever load our OWN committed file (no uploads, downloads or paths taken from a request);
* load_verified() reads the bytes once, compares their SHA-256 with EXPECTED_SHA256 below (committed,
  reviewed code) and refuses before unpickling anything if they differ;
* it then unpickles those same in-memory bytes, so the file cannot be swapped between check and load.
The checksum does not make an untrusted pickle safe; it proves this is exactly the file we built.

After a deliberate retrain, `python -m ml.train` prints the new checksum; paste it into EXPECTED_SHA256
and commit, so accepting a new model is always a reviewed code change.
"""
import hashlib
import io
import json
import platform
from importlib.metadata import version
from pathlib import Path

import joblib
import sklearn
from sklearn.pipeline import Pipeline

from ml import features
from ml.data import generate as gen

MODEL_VERSION = "noshow-1.0.0"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACT_DIR / f"{MODEL_VERSION}.joblib"
METADATA_PATH = ARTIFACT_DIR / f"{MODEL_VERSION}.json"
EXPECTED_SHA256 = "d69f7723b34fe773da3eb09841304a050bb72410654c00487b1a4f242fec8218"

LABELS = {"1": "likely_no_show", "0": "likely_attend"}
NOTICE = ("Educational demo trained on synthetic data. Not medical advice, not a diagnosis, "
          "and not a prediction about any real person or appointment.")
PACKAGES = ["scikit-learn", "numpy", "pandas", "joblib", "scipy"]
NUMBER_RANGES = {"lead_time_days": (0, 90), "hour": (8, 17), "prior_visits": (0, 20), "prior_no_shows": (0, 20)}
MAY_BE_BLANK = {"reminder_sent", "prior_visits", "prior_no_shows", "distance_band", "age_band"}


class ArtifactError(Exception):
    """The model cannot be used."""


class ArtifactUnavailable(ArtifactError):
    """The model or metadata file is missing."""


class ArtifactIntegrityError(ArtifactError):
    """The file's checksum or the metadata does not match the committed values: refused before unpickling."""


class ArtifactIncompatible(ArtifactError):
    """The installed scikit-learn is not the version the model was built with."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def model_bytes(pipeline):
    buffer = io.BytesIO()
    joblib.dump(pipeline, buffer)
    return buffer.getvalue()


def input_schema():
    """The 10 inputs, in order: type, allowed values or range, and whether they may be blank (used by the API)."""
    schema = []
    for name in features.FEATURES:
        field = {"name": name, "may_be_blank": name in MAY_BE_BLANK}
        if name in gen.CATEGORIES:
            field.update(type="category", allowed=list(gen.CATEGORIES[name]))
        else:
            low, high = NUMBER_RANGES[name]
            field.update(type="integer", min=low, max=high)
        schema.append(field)
    return schema


def build_metadata(results, model_sha256):
    chosen = results["chosen"]
    data_meta = json.loads(gen.DEFAULT_META.read_text(encoding="utf-8"))
    return {
        "model_version": MODEL_VERSION,
        "model_file": MODEL_PATH.name,
        "model_sha256": model_sha256,
        "notice": NOTICE,
        "model": {
            "type": chosen,
            "settings": results["tuning"][chosen]["best_params"],
            "fitted_on": "train",
            "steps": ["preprocess (median + was-blank column, scaling, 'missing' category, one-hot)", chosen],
        },
        "threshold": results["validation"][chosen]["threshold"],
        "threshold_rule": "best F1 on the validation pile, ties to the higher threshold",
        "labels": LABELS,
        "input_schema": input_schema(),
        "input_rules": [
            "prior_no_shows may not exceed prior_visits",
            "prior_visits and prior_no_shows are either both given or both blank",
        ],
        "training_data": {
            "file": "ml/data/appointments.csv",
            "content_sha256": data_meta["content_sha256"],
            "seed": data_meta["seed"], "rows": data_meta["rows"], "noise": data_meta["noise"],
            "split_seed": features.SPLIT_SEED,
            "pile_sizes": results["pile_sizes"],
        },
        "metrics": {
            "validation": results["validation"][chosen],
            "test": results["test"][chosen],
            "baseline_test": results["test"]["baseline"],
            "ceilings": results["ceilings"],
        },
        "environment": {"python": ".".join(platform.python_version_tuple()[:2]),
                        **{package: version(package) for package in PACKAGES}},
        "created_by": "python -m ml.train",
    }


def metadata_text(metadata):
    return json.dumps(metadata, indent=2) + "\n"


def save(data, metadata, model_path=MODEL_PATH, metadata_path=METADATA_PATH):
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    Path(model_path).write_bytes(data)
    Path(metadata_path).write_bytes(metadata_text(metadata).encode("utf-8"))


def load_verified(model_path=MODEL_PATH, metadata_path=METADATA_PATH, expected_sha256=None):
    """Return (pipeline, metadata) only if every check passes; otherwise raise an ArtifactError."""
    expected = expected_sha256 or EXPECTED_SHA256
    model_path, metadata_path = Path(model_path), Path(metadata_path)
    if not model_path.is_file() or not metadata_path.is_file():
        raise ArtifactUnavailable("The model file or its metadata is missing.")

    data = model_path.read_bytes()  # read ONCE; the checks and the unpickling use these same bytes
    digest = sha256_bytes(data)
    if digest != expected:
        raise ArtifactIntegrityError("The model file does not match the committed checksum; refusing to load it.")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("model_sha256") != digest or metadata.get("model_version") != MODEL_VERSION:
        raise ArtifactIntegrityError("The metadata does not describe this model file; refusing to load it.")
    built_with = metadata.get("environment", {}).get("scikit-learn")
    if built_with != sklearn.__version__:
        raise ArtifactIncompatible(
            f"The model was built with scikit-learn {built_with}, but {sklearn.__version__} is installed."
        )

    pipeline = joblib.load(io.BytesIO(data))
    if not isinstance(pipeline, Pipeline):
        raise ArtifactIntegrityError("The model file does not contain a scikit-learn Pipeline.")
    return pipeline, metadata
