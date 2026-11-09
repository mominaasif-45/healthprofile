"""
POST /api/llm/v1/faq/ask/: the educational FAQ assistant (phase 3: no retrieval yet).

* Members only: JWT cookie + CSRF, declared explicitly like every member view. It takes no profile id.
* Throttled per member (scope "llm_ask", 10/min in settings): every call runs a model on this computer.
* Order: sign-in, CSRF, throttle -> strict input + personal-details refusal (400) -> model call with limits ->
  strict reply schema (502) -> answer (200). Timeout 504, model unreachable or misconfigured 503.
* Errors are fixed messages: no stack trace, no raw model text, no question. Logs hold the error type only.
"""
import logging

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.authentication import CookieJWTAuthentication

from . import service
from .providers import ProviderBadReply, ProviderTimeout, ProviderUnavailable
from .schema import ReplyInvalid
from .serializers import FaqAnswerResponse, FaqQuestionRequest

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


DESCRIPTION = (
    "**Educational demo on synthetic data. Not medical advice and not a diagnosis.** Ask a short question about the "
    "HealthProfile app; a language model answers in a fixed JSON shape. Phase 3 has no policy documents yet, so many "
    "questions get `insufficient_information`; medical or unrelated questions get `out_of_scope`.\n\n"
    "Send only `{\"question\": \"...\"}` (3 to 500 characters); any other field is rejected. Questions containing "
    "personal details (email addresses, phone or ID numbers, dates of birth, your own name) are refused before "
    "anything reaches the model. Profile data is never sent. Questions and answers are not stored or logged.\n\n"
    "`usage` gives token counts (`source: provider` = counted by the model server, `estimate` = the test provider). "
    "`cost` is always 0.00: the model runs on this computer, and hardware and electricity are not counted.\n\n"
    "Errors: 400 invalid input or personal details (`fields.question`), 401 not signed in as a member, 403 missing "
    "CSRF header, 429 more than 10 questions a minute, 502 `llm_bad_reply` (the model's answer broke the schema), "
    "503 `llm_unavailable`, 504 `llm_timeout`."
)

# The real output of one local call (llama3.2:3b on CPU, cold start: the model was loaded by this call).
EXAMPLE_RESPONSE = {
    "status": "answered",
    "answer": "You can add up to three emergency contacts to your profile.",
    "provider": "ollama", "model": "llama3.2:3b", "prompt_version": "faq-system-1",
    "usage": {"prompt_tokens": 386, "completion_tokens": 24, "total_tokens": 410, "source": "provider"},
    "cost": dict(service.LOCAL_COST), "latency_ms": 36249, "disclaimer": service.DISCLAIMER,
}


class FaqAskView(APIView):
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "llm_ask"

    @extend_schema(
        tags=TAG,
        summary="Ask the FAQ assistant (educational demo, no retrieval yet)",
        description=DESCRIPTION,
        request=FaqQuestionRequest,
        responses={
            200: FaqAnswerResponse,
            400: OpenApiResponse(description="Invalid input, an unknown field, or personal details in the question."),
            401: OpenApiResponse(description="Not signed in as a member."),
            403: OpenApiResponse(description="Missing or invalid X-CSRFToken header."),
            429: OpenApiResponse(description="Too many questions (10 per minute per member)."),
            502: OpenApiResponse(description="llm_bad_reply: the model's answer did not match the required JSON shape."),
            503: OpenApiResponse(description="llm_unavailable: the model server is unreachable or not configured."),
            504: OpenApiResponse(description="llm_timeout: the model took longer than the configured timeout."),
        },
        examples=[
            OpenApiExample("Question", value={"question": "How many emergency contacts can I add?"},
                           request_only=True),
            OpenApiExample("Answer (real local call, cold start)", value=EXAMPLE_RESPONSE, response_only=True, status_codes=["200"]),
        ],
    )
    def post(self, request):
        serializer = FaqQuestionRequest(data=request.data, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        try:
            answer = service.ask(serializer.validated_data["question"])
        except ProviderTimeout:
            logger.warning("LLM call timed out")
            raise LLMTimeout() from None
        except ProviderUnavailable as exc:
            logger.warning("LLM unavailable (%s)", exc)  # a fixed reason or an error class name, never text
            raise LLMUnavailable() from None
        except (ProviderBadReply, ReplyInvalid) as exc:
            logger.warning("LLM reply rejected (%s)", exc)  # a fixed reason, never the reply
            raise LLMBadReply() from None
        return Response(answer)
