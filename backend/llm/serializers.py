"""
Request and response shapes for POST /api/llm/v1/faq/ask/.

The request is strict: exactly one field, `question`, which must be real text (not a number, list or true/false)
of 3 to 500 characters; unknown fields (for example `role`, `model` or `temperature`) are rejected, so a member can
never change the prompt or the model settings. Error messages never repeat the question.
"""
from collections.abc import Mapping

from rest_framework import serializers

from ml.serializers import UNKNOWN_FIELD

from . import privacy

MIN_QUESTION, MAX_QUESTION = 3, 500


class StrictTextField(serializers.CharField):
    default_error_messages = {
        "invalid": "Must be text.",
        "max_length": f"Must be at most {MAX_QUESTION} characters.",
        "min_length": f"Must be at least {MIN_QUESTION} characters.",
    }

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class FaqQuestionRequest(serializers.Serializer):
    question = StrictTextField(min_length=MIN_QUESTION, max_length=MAX_QUESTION)

    def to_internal_value(self, data):
        unknown = {key: [UNKNOWN_FIELD] for key in data if key not in self.fields} if isinstance(data, Mapping) else {}
        if unknown:
            raise serializers.ValidationError(unknown)
        return super().to_internal_value(data)

    def validate_question(self, value):
        if privacy.contains_personal_details(value, self.context.get("user")):
            raise serializers.ValidationError(privacy.MESSAGE)
        return value


class UsageResponse(serializers.Serializer):
    prompt_tokens = serializers.IntegerField(allow_null=True)
    completion_tokens = serializers.IntegerField(allow_null=True)
    total_tokens = serializers.IntegerField(allow_null=True)
    source = serializers.ChoiceField(
        choices=["provider", "estimate", "none"],
        help_text="provider: counted by the model server; estimate: about 4 characters per token; none: the model "
                  "was not called (nothing relevant was found). Embedding calls are not counted.")


class CostResponse(serializers.Serializer):
    amount = serializers.CharField(help_text="Always \"0.00\" for a local model.")
    currency = serializers.CharField()
    note = serializers.CharField()


class CitationResponse(serializers.Serializer):
    chunk_id = serializers.CharField(help_text="A chunk that was sent to the model; the quote was found in it.")
    document_id = serializers.IntegerField()
    document_title = serializers.CharField()
    quote = serializers.CharField()


class RetrievalResponse(serializers.Serializer):
    top_k = serializers.IntegerField()
    min_similarity = serializers.FloatField()
    chunk_size = serializers.IntegerField()
    chunk_overlap = serializers.IntegerField()
    embedding_model = serializers.CharField()
    best_similarity = serializers.FloatField(allow_null=True)
    chunks_sent = serializers.IntegerField()
    unverified_citations_removed = serializers.IntegerField()


class FaqAnswerResponse(serializers.Serializer):
    status = serializers.ChoiceField(choices=["answered", "insufficient_information", "out_of_scope"])
    answer = serializers.CharField()
    citations = CitationResponse(many=True)
    retrieval = RetrievalResponse()
    provider = serializers.CharField()
    model = serializers.CharField()
    prompt_version = serializers.CharField()
    usage = UsageResponse()
    cost = CostResponse()
    latency_ms = serializers.IntegerField()
    disclaimer = serializers.CharField()


class PolicyUploadRequest(serializers.Serializer):
    """For the docs only: the view checks the file itself (llm/extract.py)."""

    file = serializers.FileField(help_text=".txt or .md, at most 200 KB, UTF-8 text, no personal details.")


class PolicyUploadResponse(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    filename = serializers.CharField()
    sha256 = serializers.CharField()
    size_bytes = serializers.IntegerField()
    chunks = serializers.IntegerField()
    embedding_model = serializers.CharField()
    chunk_size = serializers.IntegerField()
    chunk_overlap = serializers.IntegerField()
