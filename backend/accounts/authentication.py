from django.conf import settings
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication


def enforce_csrf(request):
    """
    Reject a state-changing request unless it carries a valid CSRF token
    (X-CSRFToken header matching the csrftoken cookie).
    Needed because our JWT lives in a cookie, which browsers send automatically.
    """
    check = CSRFCheck(lambda req: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied(f"CSRF failed: {reason}")


class CookieJWTAuthentication(JWTAuthentication):
    """
    Reads the JWT access token from the HttpOnly 'access' cookie
    (instead of an Authorization header) and returns the user.
    Used ONLY on standard-user endpoints.
    """

    def authenticate(self, request):
        raw_token = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS)
        if not raw_token:
            return None  # not logged in -> endpoint answers 401

        validated_token = self.get_validated_token(raw_token)  # expired/fake -> 401
        user = self.get_user(validated_token)                  # inactive user -> 401

        # Defence in depth: JWTs are only for standard users, never admins.
        if user.role != "user":
            raise exceptions.AuthenticationFailed("This token is not valid for this account type.")

        if request.method not in ("GET", "HEAD", "OPTIONS"):
            enforce_csrf(request)

        return user, validated_token