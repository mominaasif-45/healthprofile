"""
Request and response shapes for the no-show demo endpoint.

The request serializer is BUILT FROM the model's metadata (`input_schema`), so the API accepts exactly the
inputs the model was trained on. At request time it comes from the loaded, checksum-verified model
(ml.predictor); for Swagger, the same function reads the committed metadata as plain JSON (never the pickle).

Stricter than DRF's defaults: unknown fields are rejected instead of ignored, whole numbers must really be
whole numbers (not "21", 21.0 or true), and error messages never repeat the submitted value.
"""
import json
from collections.abc import Mapping

from rest_framework import serializers

from ml import artifact

UNKNOWN_FIELD = "Unknown field."
NOT_BLANK = "This field may not be blank."


class StrictIntegerField(serializers.IntegerField):
    """Refuses text ("21"), decimals (21.5 and 21.0) and true/false, which IntegerField would quietly convert."""

    default_error_messages = {"invalid": "Must be a whole number."}

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class StrictChoiceField(serializers.ChoiceField):
    """Text only, from the allowed list; the error lists the allowed values instead of echoing the input."""

    def to_internal_value(self, data):
        if not isinstance(data, str) or data not in self.choices:
            self.fail("invalid_choice")
        return data


class NoShowRequestBase(serializers.Serializer):
    """Shared behaviour; the fields are added by serializer_from_schema()."""

    def to_internal_value(self, data):
        unknown = {key: [UNKNOWN_FIELD] for key in data if key not in self.fields} if isinstance(data, Mapping) else {}
        try:
            values = super().to_internal_value(data)
        except serializers.ValidationError as exc:
            if unknown and isinstance(exc.detail, dict):
                raise serializers.ValidationError({**exc.detail, **unknown}) from exc
            raise
        if unknown:
            raise serializers.ValidationError(unknown)
        return values

    def validate(self, attrs):
        # The two input_rules recorded in the model metadata.
        visits, no_shows = attrs.get("prior_visits"), attrs.get("prior_no_shows")
        if (visits is None) != (no_shows is None):
            raise serializers.ValidationError(
                {"prior_no_shows": ["Give both prior_visits and prior_no_shows, or leave both blank."]}
            )
        if visits is not None and no_shows > visits:
            raise serializers.ValidationError({"prior_no_shows": ["Must not be more than prior_visits."]})
        return attrs


def serializer_from_schema(schema, name="NoShowRequest"):
    """One required field per schema entry, in order; `may_be_blank` decides whether null is accepted."""
    attrs = {}
    for field in schema:
        common = {"required": True, "allow_null": field["may_be_blank"]}
        if field["type"] == "category":
            allowed = list(field["allowed"])
            attrs[field["name"]] = StrictChoiceField(
                choices=allowed, **common,
                error_messages={"null": NOT_BLANK, "invalid_choice": f"Must be one of: {', '.join(allowed)}."},
            )
        elif field["type"] == "integer":
            low, high = field["min"], field["max"]
            between = f"Must be between {low} and {high}."
            attrs[field["name"]] = StrictIntegerField(
                min_value=low, max_value=high, **common,
                error_messages={"null": NOT_BLANK, "min_value": between, "max_value": between},
            )
        else:
            raise ValueError(f"Unknown field type in the model schema: {field['type']}")
    return type(name, (NoShowRequestBase,), attrs)


def _schema_for_docs():
    """The committed metadata's input schema, read as JSON only. Missing file: no fields (the API answers 503)."""
    try:
        return json.loads(artifact.METADATA_PATH.read_text(encoding="utf-8"))["input_schema"]
    except (OSError, ValueError, KeyError):
        return []


NoShowRequestDocs = serializer_from_schema(_schema_for_docs())


class NoShowResponse(serializers.Serializer):
    prediction = serializers.ChoiceField(
        choices=list(artifact.LABELS.values()),
        help_text="likely_no_show when probability >= threshold, otherwise likely_attend.",
    )
    probability = serializers.FloatField(help_text="Model's no-show probability (0 to 1), rounded to 4 decimals.")
    threshold = serializers.FloatField(help_text="Decision threshold chosen on the validation data.")
    model_version = serializers.CharField(help_text="Which model file answered, e.g. noshow-1.0.0.")
    disclaimer = serializers.CharField(help_text="Educational demo on synthetic data; not medical advice.")
