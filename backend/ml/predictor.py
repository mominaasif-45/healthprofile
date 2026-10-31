"""
Loads the checksum-verified model ONCE (on the first request) and turns validated inputs into a prediction.

A failed load is not cached: the next request tries again, so fixing the file needs no restart. Only the
error's class name is logged. Inputs, probabilities and predictions are never logged or stored.
"""
import logging
import threading
from dataclasses import dataclass

import pandas as pd
from rest_framework import status
from rest_framework.exceptions import APIException

from ml import artifact, features
from ml.serializers import serializer_from_schema

logger = logging.getLogger(__name__)


class ModelUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The demo model is unavailable right now. Please try again later."
    default_code = "model_unavailable"


@dataclass(frozen=True)
class Predictor:
    pipeline: object
    metadata: dict
    serializer_class: type

    def predict(self, values):
        row = pd.DataFrame([values], columns=features.FEATURES)
        probability = float(self.pipeline.predict_proba(row)[:, 1][0])
        threshold = self.metadata["threshold"]
        return {
            "prediction": self.metadata["labels"]["1" if probability >= threshold else "0"],
            "probability": round(probability, 4),
            "threshold": threshold,
            "model_version": self.metadata["model_version"],
            "disclaimer": self.metadata["notice"],
        }


_lock = threading.Lock()
_predictor = None


def get_predictor():
    global _predictor
    if _predictor is None:
        with _lock:  # two simultaneous first requests still load only once
            if _predictor is None:
                try:
                    pipeline, metadata = artifact.load_verified(artifact.MODEL_PATH, artifact.METADATA_PATH)
                except Exception as exc:  # any failure to load means the demo is unavailable
                    logger.error("No-show demo model could not be loaded (%s)", type(exc).__name__)
                    raise ModelUnavailable() from exc
                _predictor = Predictor(pipeline, metadata, serializer_from_schema(metadata["input_schema"]))
    return _predictor


def reset():
    """Forget the loaded model (tests; or after deliberately replacing the file)."""
    global _predictor
    with _lock:
        _predictor = None
