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
    "django.contrib.postgres",  # ArrayField for policy chunk embeddings (part of Django, no new package)
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
    "llm",  # Week 4: policy documents and chunks for the FAQ assistant
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
    "DEFAULT_THROTTLE_RATES": {"login": "5/min", "ml_predict": "30/min", "ml_reports": "60/min",
                               "llm_ask": "10/min", "llm_upload": "20/min"},
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

# ---------- LLM FAQ assistant (Week 4) ----------
# "fake" (default: tests and CI, no network) or "ollama" (a local Ollama server; set it in your own .env only).
LLM_PROVIDER = env("LLM_PROVIDER", default="fake")
LLM_BASE_URL = env("LLM_BASE_URL", default="http://127.0.0.1:11434")  # must be this machine (checked)
LLM_MODEL = env("LLM_MODEL", default="llama3.2:3b")
LLM_TIMEOUT_SECONDS = env.float("LLM_TIMEOUT_SECONDS", default=100.0)  # measured with retrieval (CPU):
# cold 36-49 s, warm about 27 s (phase 3 without documents: cold 28-36 s, warm 7-11 s)
LLM_MAX_TOKENS = 300        # reply limit (Ollama num_predict); room for the answer and up to 3 quotes
LLM_TEMPERATURE = 0.2       # low: short factual answers, little variation
LLM_CONTEXT_TOKENS = 2048   # small fixed context window keeps the local model's memory low
# Retrieval (phase 4). Embedder: "fake" (hashing, no network) or "ollama" (nomic-embed-text); follows LLM_PROVIDER.
LLM_EMBEDDER = env("LLM_EMBEDDER", default=LLM_PROVIDER)
LLM_EMBED_MODEL = env("LLM_EMBED_MODEL", default="nomic-embed-text")
LLM_EMBED_TIMEOUT_SECONDS = env.float("LLM_EMBED_TIMEOUT_SECONDS", default=60.0)
# Settings so phase 5 can compare two retrieval set-ups (env overrides for experiments only).
LLM_CHUNK_SIZE = env.int("LLM_CHUNK_SIZE", default=600)            # characters per chunk
LLM_CHUNK_OVERLAP = env.int("LLM_CHUNK_OVERLAP", default=100)      # characters shared by neighbouring chunks
LLM_TOP_K = env.int("LLM_TOP_K", default=3)                        # chunks sent to the model at most
LLM_MIN_SIMILARITY = env.float("LLM_MIN_SIMILARITY", default=0.62)  # cosine, set for nomic-embed-text:
# 14 probe questions: covered 0.634-0.770, not covered 0.426-0.607. Narrow gap; the citation check is the main guard.

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
        # Profile age_range and the ML demo's age_band share these six values: one name for both.
        "AgeRangeEnum": "profiles.models.Demographics.AgeRange",
    },
}