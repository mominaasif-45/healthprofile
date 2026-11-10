"""
POST /api/llm/v1/faq/ask/: the educational FAQ assistant, answering from approved fictional policies (RAG).

* Members only: JWT cookie + CSRF, declared explicitly like every member view. It takes no profile id.
* Throttled per member (scope "llm_ask", 10/min in settings): every call runs models on this computer.
* Order: sign-in, CSRF, throttle -> strict input + personal-details refusal (400) -> retrieval -> model call with
  limits -> strict reply schema (502) -> citation check -> answer (200). Timeout 504, unreachable or misconfigured 503.

POST /api/llm/v1/policies/: upload one policy file (admins only: session + CSRF, like every admin route).
* .txt / .md, at most 200 KB, UTF-8, no personal details (400); the same content twice (409); embedder down (503).

Errors are fixed messages: no stack trace, no raw model text, no question or file content. Logs hold the error type
only.
"""
import logging

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.authentication import CookieJWTAuthentication
from adminpanel.permissions import IsAdminRole
from ml.serializers import UNKNOWN_FIELD

from . import extract, ingest, privacy, service
from .providers import ProviderBadReply, ProviderError, ProviderTimeout, ProviderUnavailable
from .schema import ReplyInvalid
from .serializers import FaqAnswerResponse, FaqQuestionRequest, PolicyUploadRequest, PolicyUploadResponse

TAG = ["llm faq (educational)"]
logger = logging.getLogger(__name__)


class LLMUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The assistant is unavailable right now. Please try again later."
    default_code = "llm_unavailable"


class LLMTimeout(APIException):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    default_detail = "The assistant took too long to answer. Please try again."
    default_code = "llm_timeout"


class LLMBadReply(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "The assistant's answer could not be used. Please try again or rephrase your question."
    default_code = "llm_bad_reply"


class DuplicatePolicy(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This document has already been uploaded."
    default_code = "duplicate_document"


def provider_errors_to_api(call):
    """Run call(); turn provider and reply errors into safe API errors, logging only a fixed reason."""
    try:
        return call()
    except ProviderTimeout:
        logger.warning("LLM call timed out")
        raise LLMTimeout() from None
    except ProviderUnavailable as exc:
        logger.warning("LLM unavailable (%s)", exc)  # a fixed reason or an error class name, never text
        raise LLMUnavailable() from None
    except (ProviderBadReply, ReplyInvalid) as exc:
        logger.warning("LLM reply rejected (%s)", exc)  # a fixed reason, never the reply
        raise LLMBadReply() from None


DESCRIPTION = (
    "**Educational demo on synthetic data. Not medical advice and not a diagnosis.** Ask a short question about the "
    "fictional HealthProfile demo policies. The server finds the most similar policy passages, sends them to a "
    "language model as untrusted reference text, and checks every citation it returns: the passage must have been "
    "sent, and the quote must appear in it. Unverified citations are removed.\n\n"
    "If no passage is similar enough, or the answer has no verified citation, the status is "
    "`insufficient_information` and the answer is a fixed sentence (the model is not allowed to guess). Medical or "
    "unrelated questions get `out_of_scope` with a fixed sentence.\n\n"
    "Send only `{\"question\": \"...\"}` (3 to 500 characters); any other field is rejected. Questions containing "
    "personal details (email addresses, phone or ID numbers, dates of birth, your own name) are refused before "
    "anything reaches a model. Profile data is never sent. Questions and answers are not stored or logged.\n\n"
    "`retrieval` shows the settings used and how many passages were sent. `usage` gives the chat model's token "
    "counts (`provider` = counted by the model server, `estimate` = the test provider, `none` = not called). `cost` "
    "is always 0.00: the models run on this computer, and hardware and electricity are not counted.\n\n"
    "Errors: 400 invalid input or personal details (`fields.question`), 401 not signed in as a member, 403 missing "
    "CSRF header, 429 more than 10 questions a minute, 502 `llm_bad_reply` (the model's answer broke the schema), "
    "503 `llm_unavailable`, 504 `llm_timeout`."
)

# A real local call (llama3.2:3b + nomic-embed-text on CPU, seeded demo policies). latency_ms is the measured
# 35.6 s wall time, rounded; the chat model had to load first.
EXAMPLE_RESPONSE = {
    "status": "answered",
    "answer": "A member can add up to three emergency contacts to a profile.",
    "citations": [{"chunk_id": "3", "document_id": 2, "document_title": "Emergency contacts",
                   "quote": "A member can add up to three emergency contacts to a profile."}],
    "retrieval": {"top_k": 3, "min_similarity": 0.62, "chunk_size": 600, "chunk_overlap": 100,
                  "embedding_model": "ollama:nomic-embed-text", "best_similarity": 0.7841, "chunks_sent": 3,
                  "unverified_citations_removed": 0},
    "provider": "ollama", "model": "llama3.2:3b", "prompt_version": "faq-system-2",
    "usage": {"prompt_tokens": 706, "completion_tokens": 54, "total_tokens": 760, "source": "provider"},
    "cost": dict(service.LOCAL_COST), "latency_ms": 35600, "disclaimer": service.DISCLAIMER,
}


class FaqAskView(APIView):
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "llm_ask"

    @extend_schema(
        tags=TAG,
        summary="Ask the FAQ assistant (answers only from fictional demo policies, with checked citations)",
        description=DESCRIPTION,
        request=FaqQuestionRequest,
        responses={
            200: FaqAnswerResponse,
            400: OpenApiResponse(description="Invalid input, an unknown field, or personal details in the question."),
            401: OpenApiResponse(description="Not signed in as a member."),
            403: OpenApiResponse(description="Missing or invalid X-CSRFToken header."),
            429: OpenApiResponse(description="Too many questions (10 per minute per member)."),
            502: OpenApiResponse(description="llm_bad_reply: the model's answer did not match the required JSON shape."),
            503: OpenApiResponse(description="llm_unavailable: a model server is unreachable or not configured."),
            504: OpenApiResponse(description="llm_timeout: a model took longer than the configured timeout."),
        },
        examples=[
            OpenApiExample("Question", value={"question": "How many emergency contacts can I add?"},
                           request_only=True),
            OpenApiExample("Answer with a verified citation (real local call)", value=EXAMPLE_RESPONSE,
                           response_only=True, status_codes=["200"]),
        ],
    )
    def post(self, request):
        serializer = FaqQuestionRequest(data=request.data, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        answer = provider_errors_to_api(lambda: service.ask(serializer.validated_data["question"]))
        return Response(answer)


class PolicyUploadView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "llm_upload"

    @extend_schema(
        tags=TAG,
        summary="Upload a fictional policy document (admins only)",
        description=(
            "**Admins only** (session + CSRF). Send one file in the `file` field: `.txt` or `.md`, at most 200 KB, "
            "valid UTF-8, with no personal details (email addresses, phone or ID numbers, dates written with "
            "digits), because its text is sent to the assistant. The file is split into chunks (size and overlap "
            "from settings), each chunk is embedded, and all of it is stored in one transaction.\n\n"
            "Errors: 400 wrong type, too big, not UTF-8, binary, empty, personal details or an unknown field "
            "(`fields.file`); 403 not an admin or missing CSRF header; 409 `duplicate_document`; 429 more than 20 "
            "uploads a minute; 503 `llm_unavailable` (the embedding model is unreachable: nothing is stored)."
        ),
        request={"multipart/form-data": PolicyUploadRequest},
        responses={
            201: PolicyUploadResponse,
            400: OpenApiResponse(description="Not an acceptable file (see `fields.file`), or an unknown field."),
            403: OpenApiResponse(description="Not signed in as an admin, or missing X-CSRFToken header."),
            409: OpenApiResponse(description="duplicate_document: the same content is already stored."),
            429: OpenApiResponse(description="Too many uploads (20 per minute)."),
            503: OpenApiResponse(description="llm_unavailable: the embedding model is unreachable; nothing stored."),
            504: OpenApiResponse(description="llm_timeout: the embedding model took too long; nothing stored."),
        },
    )
    def post(self, request):
        unknown = {key: [UNKNOWN_FIELD] for key in request.data if key != "file"}
        if unknown:
            raise serializers.ValidationError(unknown)
        files = request.FILES.getlist("file")
        if len(files) != 1:
            raise serializers.ValidationError({"file": ["Send exactly one file in the 'file' field."]})
        upload = files[0]
        if upload.size > extract.MAX_BYTES:  # refuse before reading it into memory
            raise serializers.ValidationError({"file": [extract.TOO_BIG]})
        try:
            extracted = extract.extract_text(upload.name, upload.read(extract.MAX_BYTES + 1))
        except extract.ExtractError as exc:
            raise serializers.ValidationError({"file": [str(exc)]}) from None
        if privacy.contains_personal_details(extracted.text):
            raise serializers.ValidationError({"file": [privacy.DOCUMENT_MESSAGE]})

        def store():
            return ingest.ingest_document(filename=extract.PurePath(upload.name).name, title=extracted.title,
                                          text=extracted.text, source="upload", uploaded_by=request.user)
        try:
            document = provider_errors_to_api(store)
        except ingest.DuplicateDocument:
            raise DuplicatePolicy() from None
        except ProviderError:  # any other provider error (defensive): nothing was stored
            raise LLMUnavailable() from None
        return Response({
            "id": document.id, "title": document.title, "filename": document.filename, "sha256": document.sha256,
            "size_bytes": document.size_bytes, "chunks": document.chunks.count(),
            "embedding_model": document.embedding_model, "chunk_size": document.chunk_size,
            "chunk_overlap": document.chunk_overlap,
        }, status=status.HTTP_201_CREATED)
