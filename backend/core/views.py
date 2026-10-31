from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(
    tags=["system"], summary="Health check", description="Returns ok while the API is running. No sign-in needed.",
    responses=inline_serializer("Health", {"status": serializers.CharField()}),
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """Simple check that the API is running."""
    return Response({"status": "ok"})


@extend_schema(
    tags=["system"], summary="Get a CSRF token",
    description="Sets the `csrftoken` cookie. Send its value back in the X-CSRFToken header on every "
                "POST / PUT / PATCH / DELETE. Django rotates the token when an admin signs in, so call this again afterwards.",
    responses=inline_serializer("CsrfToken", {"csrfToken": serializers.CharField()}),
)
@ensure_csrf_cookie
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def csrf(request):
    """
    Sets the 'csrftoken' cookie. The frontend calls this once, then sends
    the token back in the X-CSRFToken header on every POST/PATCH.
    """
    return Response({"csrfToken": get_token(request)})