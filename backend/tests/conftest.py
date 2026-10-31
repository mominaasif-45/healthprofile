import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts.models import User
from profiles import services
from profiles.models import (
    Demographics,
    EmergencyContact,
    HealthProfile,
    WellnessGoal,
    WellnessPreference,
)

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
    return User.objects.create_user(email="momina@example.com", password=PASSWORD, name="Momina Asif")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(email="bilal@example.com", password=PASSWORD, name="Bilal Ahmed")


@pytest.fixture
def admin(db):
    return User.objects.create_admin(email="admin@example.com", password=PASSWORD, name="Admin")


def make_profile(user, full_name=None, status="active", sections=("demographics", "contact", "wellness", "goal")):
    """
    Build a profile directly in the database (no API), with any of the 4 sections.
    The default is a COMPLETE profile (100%). Pass sections=() for an empty one.
    """
    profile = HealthProfile.objects.create(user=user, status=status)
    if "demographics" in sections:
        Demographics.objects.create(
            profile=profile, full_name=full_name or user.name, age_range="25-34", city="Lahore",
            date_of_birth="1995-06-15",
        )
    if "contact" in sections:
        EmergencyContact.objects.create(
            profile=profile, name="Sana Ahmed", relationship="sibling", phone="+923001234567", is_primary=True
        )
    preference = None
    if "wellness" in sections or "goal" in sections:
        preference = WellnessPreference.objects.create(
            profile=profile, contact_preference="email", allergies="Peanuts", lifestyle_notes="Secret note",
            activity_level="moderate", diet_preference="halal", sleep_goal_hours=8,
        )
    if "goal" in sections:
        WellnessGoal.objects.create(preference=preference, goal="better_sleep")
    services.recalculate_completion(profile)
    return profile


@pytest.fixture
def profile(user):
    return make_profile(user)


@pytest.fixture
def empty_profile(user):
    return make_profile(user, sections=())


def user_login(client, email="momina@example.com", password=PASSWORD):
    return client.post("/api/auth/user/login/", {"email": email, "password": password}, format="json")


def admin_login(client, email="admin@example.com", password=PASSWORD):
    return client.post("/api/admin/login/", {"email": email, "password": password}, format="json")


def csrf_header(client):
    """Fetch the csrftoken cookie and return the header a browser would send."""
    client.get("/api/csrf/")
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}
