"""
HealthProfile - Django settings.
Secrets and environment-specific values come from backend/.env
(see .env.example). Nothing secret is written in this file.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------- Environment ----------
env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------- Apps ----------
INSTALLED_APPS = [
    # Django built-ins (no django.contrib.admin: admins use our own session login)
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    # Our apps
    "core",
    "accounts",
    "profiles",
    "adminpanel",
    "audit",
]

MIDDLEWARE = [
    "core.middleware.RequestIdMiddleware",  # first, so every response carries X-Request-ID
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------- Database (PostgreSQL, from DATABASE_URL in .env) ----------
DATABASES = {"default": env.db("DATABASE_URL")}

# ---------- Users and passwords ----------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------- Locale ----------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------- Django REST Framework ----------
REST_FRAMEWORK = {
    # Secure by default: every view must explicitly choose its own
    # authentication (JWT for users, session for admins).
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_THROTTLE_RATES": {"login": "5/min"},
           "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
}

# ---------- JWT (standard users) ----------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("JWT_SIGNING_KEY"),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# Cookie settings for the JWT cookies (used by our own login view)
AUTH_COOKIE_ACCESS = "access"
AUTH_COOKIE_REFRESH = "refresh"
AUTH_COOKIE_REFRESH_PATH = "/api/auth/user/"
AUTH_COOKIE_SECURE = not DEBUG
AUTH_COOKIE_SAMESITE = "Lax"

# ---------- Sessions (admins) ----------
SESSION_COOKIE_AGE = 60 * 30            # 30 minutes
SESSION_SAVE_EVERY_REQUEST = True       # idle timeout: each request resets the 30 min
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG

# ---------- CSRF ----------
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False            # frontend must read it to send X-CSRFToken
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=["http://localhost:3000", "http://127.0.0.1:3000"]
)

# ---------- API docs (Swagger) ----------
SPECTACULAR_SETTINGS = {
    "TITLE": "HealthProfile API",
    "DESCRIPTION": "Role-based HealthTech profile builder. Users: JWT in HttpOnly cookies. "
                   "Admins: server-side sessions. Synthetic data only.",
    "VERSION": "2.0.0",
    # Give the shared choice lists stable names in the docs (otherwise they get hash-like names).
    "ENUM_NAME_OVERRIDES": {
        "ProfileStatusEnum": "profiles.models.HealthProfile.Status",
        "CompletionStatusEnum": "profiles.models.HealthProfile.CompletionStatus",
    },
}