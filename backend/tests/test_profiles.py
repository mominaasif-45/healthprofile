import time

import pytest

from profiles.models import HealthProfile

from .conftest import make_profile, user_login

URL = "/api/profiles/me/"
NEW = {
    "full_name": "Ayesha Khan",
    "age_range": "25-34",
    "contact_preference": "email",
    "wellness_goals": ["Sleep 7+ hours", "Walk 8,000 steps"],
    "emergency_contact_name": "Bilal Ahmed",
    "emergency_contact_phone": "+92 300 0000000",
}


@pytest.mark.django_db
def test_no_cookie_returns_401(client):
    assert client.get(URL).status_code == 401


@pytest.mark.django_db
def test_get_without_profile_returns_404(client, user):
    user_login(client)
    assert client.get(URL).status_code == 404


@pytest.mark.django_db
def test_create_then_read_profile(client, user):
    user_login(client)
    res = client.post(URL, NEW, format="json")
    assert res.status_code == 201
    assert res.data["status"] == "active"
    assert res.data["completeness"]["percent"] == 60
    assert client.get(URL).data["full_name"] == "Ayesha Khan"


@pytest.mark.django_db
def test_second_create_returns_409(client, user, profile):
    user_login(client)
    assert client.post(URL, NEW, format="json").status_code == 409


@pytest.mark.django_db
def test_user_only_sees_own_profile_and_no_route_to_others(client, user, other_user):
    make_profile(user, full_name="Ayesha Khan")
    other = make_profile(other_user, full_name="Bilal Ahmed")
    user_login(client)
    assert client.get(URL).data["full_name"] == "Ayesha Khan"
    # No /profiles/{id}/ route exists at all, so another member's id can't be read.
    assert client.get(f"/api/profiles/{other.id}/").status_code == 404
    assert client.get(f"/api/profiles/me/?id={other.id}").data["full_name"] == "Ayesha Khan"


@pytest.mark.django_db
def test_patch_changes_one_field_only(client, user, profile):
    user_login(client)
    before = client.get(URL).data
    time.sleep(0.01)
    res = client.patch(URL, {"allergies": "Peanuts"}, format="json")
    assert res.status_code == 200
    after = res.data
    assert after["allergies"] == "Peanuts"
    assert after["updated_at"] > before["updated_at"]
    for field in ("full_name", "age_range", "contact_preference", "wellness_goals", "created_at"):
        assert after[field] == before[field]


@pytest.mark.django_db
def test_future_date_of_birth_returns_400(client, user, profile):
    user_login(client)
    res = client.patch(URL, {"date_of_birth": "2999-01-01"}, format="json")
    assert res.status_code == 400
    assert "date_of_birth" in res.json()["error"]["fields"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "bad",
    [
        {"contact_preference": "pigeon"},
        {"age_range": "200-300"},
        {"emergency_contact_phone": "call me maybe"},
        {"full_name": " "},
        {"allergies": "x" * 501},
        {"wellness_goals": "not a list"},
    ],
)
def test_invalid_values_return_400(client, user, profile, bad):
    user_login(client)
    assert client.patch(URL, bad, format="json").status_code == 400


@pytest.mark.django_db
def test_needs_age_range_or_date_of_birth(client, user):
    user_login(client)
    res = client.post(URL, {"full_name": "Ayesha Khan"}, format="json")
    assert res.status_code == 400
    assert "age_range" in res.json()["error"]["fields"]


@pytest.mark.django_db
def test_status_cannot_be_set_by_owner(client, user, profile):
    user_login(client)
    client.patch(URL, {"status": "deactivated"}, format="json")
    profile.refresh_from_db()
    assert profile.status == "active"


@pytest.mark.django_db
def test_deactivated_profile_cannot_be_edited_by_owner(client, user, profile):
    HealthProfile.objects.filter(pk=profile.pk).update(status="deactivated")
    user_login(client)
    assert client.patch(URL, {"allergies": "None"}, format="json").status_code == 403
