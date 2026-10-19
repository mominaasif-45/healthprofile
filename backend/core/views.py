from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """Simple check that the API is running."""
    return Response({"status": "ok"})


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