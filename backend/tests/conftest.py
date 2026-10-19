import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts.models import User
from profiles.models import HealthProfile

PASSWORD = "CalmMorning2026"


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """Login is throttled to 5/min; start every test with a clean counter."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _fast_password_hasher(settings):
    """Tests only: a fast hasher keeps the suite quick. Production keeps Django's default."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def csrf_client():
    """A client that really enforces CSRF, like a browser."""
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def user(db):
    return User.objects.create_user(email="ayesha@example.com", password=PASSWORD, name="Ayesha Khan")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(email="bilal@example.com", password=PASSWORD, name="Bilal Ahmed")


@pytest.fixture
def admin(db):
    return User.objects.create_admin(email="admin@example.com", password=PASSWORD, name="Admin")


def make_profile(user, **overrides):
    data = dict(
        full_name=user.name,
        age_range="25-34",
        contact_preference="email",
        wellness_goals=["Sleep 7+ hours"],
    )
    data.update(overrides)
    return HealthProfile.objects.create(user=user, **data)


@pytest.fixture
def profile(user):
    return make_profile(user)


def user_login(client, email="ayesha@example.com", password=PASSWORD):
    return client.post("/api/auth/user/login/", {"email": email, "password": password}, format="json")


def admin_login(client, email="admin@example.com", password=PASSWORD):
    return client.post("/api/admin/login/", {"email": email, "password": password}, format="json")


def csrf_header(client):
    """Fetch the csrftoken cookie and return the header a browser would send."""
    client.get("/api/csrf/")
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}
