import pytest

from accounts.models import User

URL = "/api/auth/signup/"
GOOD = {"name": "Sara Noor", "email": "sara@example.com", "password": "CalmMorning2026"}


@pytest.mark.django_db
def test_valid_signup_creates_user_with_hashed_password(client):
    res = client.post(URL, GOOD, format="json")
    assert res.status_code == 201
    assert "password" not in res.data
    user = User.objects.get(email="sara@example.com")
    assert user.password != GOOD["password"]
    assert "$" in user.password  # algorithm$salt$hash, never the plain text
    assert user.check_password(GOOD["password"])


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload, bad_field",
    [
        ({}, "name"),
        ({"name": "Sara"}, "email"),
        ({**GOOD, "email": "not-an-email"}, "email"),
        ({**GOOD, "password": "short"}, "password"),
        ({**GOOD, "password": "1234567890123"}, "password"),
        ({**GOOD, "password": "password123"}, "password"),
    ],
)
def test_invalid_signup_returns_400_with_field_errors(client, payload, bad_field):
    res = client.post(URL, payload, format="json")
    assert res.status_code == 400
    body = res.json()["error"]
    assert body["code"] == "validation_error"
    assert bad_field in body["fields"]


@pytest.mark.django_db
def test_duplicate_email_in_any_case_returns_409(client):
    assert client.post(URL, GOOD, format="json").status_code == 201
    res = client.post(URL, {**GOOD, "email": "SARA@Example.com"}, format="json")
    assert res.status_code == 409
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_role_in_body_is_ignored(client):
    res = client.post(URL, {**GOOD, "role": "admin", "is_staff": True, "is_superuser": True}, format="json")
    assert res.status_code == 201
    user = User.objects.get(email="sara@example.com")
    assert user.role == "user"
    assert not user.is_staff and not user.is_superuser
