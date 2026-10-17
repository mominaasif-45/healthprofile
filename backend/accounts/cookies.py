from django.conf import settings


def _seconds(setting_name):
    return int(settings.SIMPLE_JWT[setting_name].total_seconds())


def set_auth_cookies(response, access_token, refresh_token):
    """Put both JWTs in HttpOnly cookies. JavaScript can never read them."""
    common = {
        "httponly": True,
        "secure": settings.AUTH_COOKIE_SECURE,      # True in production (HTTPS only)
        "samesite": settings.AUTH_COOKIE_SAMESITE,  # "Lax": not sent on cross-site POSTs
    }
    response.set_cookie(
        settings.AUTH_COOKIE_ACCESS, access_token,
        max_age=_seconds("ACCESS_TOKEN_LIFETIME"), path="/", **common,
    )
    # The refresh cookie is only sent to /api/auth/user/... (refresh + logout)
    response.set_cookie(
        settings.AUTH_COOKIE_REFRESH, refresh_token,
        max_age=_seconds("REFRESH_TOKEN_LIFETIME"),
        path=settings.AUTH_COOKIE_REFRESH_PATH, **common,
    )


def clear_auth_cookies(response):
    response.delete_cookie(
        settings.AUTH_COOKIE_ACCESS, path="/", samesite=settings.AUTH_COOKIE_SAMESITE
    )
    response.delete_cookie(
        settings.AUTH_COOKIE_REFRESH,
        path=settings.AUTH_COOKIE_REFRESH_PATH,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )