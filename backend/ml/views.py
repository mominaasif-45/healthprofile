"""
POST /api/ml/v1/no-show/predict/: the educational no-show likelihood demo.

* Members only: JWT cookie + CSRF (declared explicitly, like every member view). It never reads or writes
  profile data and takes no profile id, so members with no profile or a deactivated one may use it.
* Throttled per member (scope "ml_predict", 30/min in settings).
* Order: sign-in, CSRF, throttle -> load the verified model (503) -> validate (400) -> predict (200).
* Nothing is stored, audited or logged: the inputs are fictional and nothing changes.
"""
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.authentication import CookieJWTAuthentication

from .artifact import NOTICE
from .predictor import get_predictor
from .serializers import NoShowRequestDocs, NoShowResponse

TAG = ["ml demo (educational)"]

# Real outputs of noshow-1.0.0 (a test sends each request and checks the response is exactly this).
EXAMPLES = [
    (
        {"lead_time_days": 21, "weekday": "mon", "hour": 9, "visit_type": "new_visit", "booking_channel": "online",
         "reminder_sent": "no", "prior_visits": 3, "prior_no_shows": 1, "distance_band": "15_30km", "age_band": None},
        {"prediction": "likely_no_show", "probability": 0.5279, "threshold": 0.22, "model_version": "noshow-1.0.0",
         "disclaimer": NOTICE},
    ),
    (
        {"lead_time_days": 3, "weekday": "thu", "hour": 11, "visit_type": "follow_up", "booking_channel": "phone",
         "reminder_sent": "yes", "prior_visits": 4, "prior_no_shows": 0, "distance_band": "under_5km",
         "age_band": "45-54"},
        {"prediction": "likely_attend", "probability": 0.0505, "threshold": 0.22, "model_version": "noshow-1.0.0",
         "disclaimer": NOTICE},
    ),
]

DESCRIPTION = (
    "**Educational demo on synthetic data. Not medical advice, not a diagnosis, and not a prediction about any "
    "real person or appointment.** Send the 10 facts of a *fictional* appointment; the model (trained only on "
    "invented data) returns the chance it would be missed.\n\n"
    "`v1` in the URL is the version of this request/response contract; `model_version` in the response says "
    "which model file answered (a retrained model changes it, not the URL).\n\n"
    "Every field is required. `null` means blank and is accepted only for `reminder_sent`, `prior_visits`, "
    "`prior_no_shows`, `distance_band` and `age_band`. `prior_no_shows` may not exceed `prior_visits`, and the "
    "two are given or blank together. Unknown fields are rejected. Inputs are not stored or logged.\n\n"
    "Errors: 400 invalid input (`fields` names each problem), 401 not signed in as a member, 403 missing CSRF "
    "header, 429 more than 30 requests a minute, 503 `model_unavailable` (the verified model could not be loaded)."
)


class NoShowPredictView(APIView):
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ml_predict"

    @extend_schema(
        tags=TAG,
        summary="Predict synthetic no-show likelihood (educational demo)",
        description=DESCRIPTION,
        request=NoShowRequestDocs,
        responses={
            200: NoShowResponse,
            400: OpenApiResponse(description="Invalid input: missing, wrong type, out of range, not allowed or unknown fields."),
            401: OpenApiResponse(description="Not signed in as a member."),
            403: OpenApiResponse(description="Missing or invalid X-CSRFToken header."),
            429: OpenApiResponse(description="Too many requests (30 per minute per member)."),
            503: OpenApiResponse(description="model_unavailable: the checksum-verified model could not be loaded."),
        },
        examples=[
            OpenApiExample("Fictional appointment (likely no-show)", value=EXAMPLES[0][0], request_only=True),
            OpenApiExample("Fictional appointment (likely attend)", value=EXAMPLES[1][0], request_only=True),
            OpenApiExample("Likely no-show", value=EXAMPLES[0][1], response_only=True, status_codes=["200"]),
            OpenApiExample("Likely attend", value=EXAMPLES[1][1], response_only=True, status_codes=["200"]),
        ],
    )
    def post(self, request):
        predictor = get_predictor()
        serializer = predictor.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(predictor.predict(serializer.validated_data))
