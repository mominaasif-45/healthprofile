"""
Teaches Swagger about our cookie-based JWT login, so every member endpoint shows its auth
requirement ("cookieAuth") instead of an "unresolved authenticator" warning.
(Admin session auth is already understood by drf-spectacular as "cookieAuth"-style sessionid.)
"""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CookieJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "accounts.authentication.CookieJWTAuthentication"
    name = "memberJwtCookie"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": "access",
            "description": (
                "Member JWT in the HttpOnly `access` cookie, set by POST /api/auth/user/login/. "
                "State-changing requests also need the X-CSRFToken header."
            ),
        }
