"""
Member root-profile behaviour and role boundaries.

(Rewritten for Week 2: the Week 1 tests PATCHed columns that now live in section tables.
 Their intent is kept here: no cookie -> 401, own data only, no route to others, 409 on a
 second create, owner cannot set status/role, deactivated profiles are read-only.)
"""
import pytest

from audit.models import AuditEvent
from profiles.models import HealthProfile

from .conftest import csrf_header, make_profile, user_login

ROOT = "/api/profiles/me/"
DEMO = {"full_name": "Momina Asif", "age_range": "25-34"}
WELLNESS = {"contact_preference": "email", "goals": ["better_sleep"]}
CONTACT = {"name": "Bilal Ahmed", "relationship": "sibling", "phone": "+92 300 0000001"}

# (method, url, body) for EVERY member route
ALL_MEMBER_ROUTES = [
    ("get", ROOT, None), ("post", ROOT, None), ("delete", ROOT, None),
    ("get", ROOT + "demographics/", None), ("put", ROOT + "demographics/", DEMO),
    ("patch", ROOT + "demographics/", {"city": "Lahore"}),
    ("get", ROOT + "wellness/", None), ("put", ROOT + "wellness/", WELLNESS),
    ("patch", ROOT + "wellness/", {"goals": []}),
    ("get", ROOT + "emergency-contacts/", None), ("post", ROOT + "emergency-contacts/", CONTACT),
    ("get", ROOT + "emergency-contacts/1/", None), ("patch", ROOT + "emergency-contacts/1/", {"name": "X Y"}),
    ("delete", ROOT + "emergency-contacts/1/", None), ("get", ROOT + "activity/", None),
]


@pytest.mark.django_db
@pytest.mark.parametrize("method,url,body", ALL_MEMBER_ROUTES)
def test_no_cookie_returns_401_on_every_member_route(client, method, url, body):
    res = getattr(client, method)(url, body, format="json")
    assert res.status_code == 401


@pytest.mark.django_db
def test_get_without_profile_returns_404(client, user):
    user_login(client)
    for url in (ROOT, ROOT + "demographics/", ROOT + "wellness/", ROOT + "emergency-contacts/"):
        assert client.get(url).status_code == 404, url


@pytest.mark.django_db
def test_create_empty_profile_then_read_it(client, user):
    user_login(client)
    res = client.post(ROOT, format="json")
    assert res.status_code == 201
    assert res.data["status"] == "active"
    assert res.data["completion"]["percent"] == 0 and res.data["completion"]["status"] == "not_started"
    assert res.data["demographics"] is None and res.data["wellness"] is None
    assert res.data["emergency_contacts"] == []
    assert client.get(ROOT).status_code == 200


@pytest.mark.django_db
def test_second_create_returns_409(client, user, profile):
    user_login(client)
    assert client.post(ROOT, format="json").status_code == 409


@pytest.mark.django_db
def test_owner_cannot_choose_status_or_role_at_create(client, user):
    user_login(client)
    res = client.post(ROOT, {"status": "deactivated", "role": "admin", "completion_percent": 100}, format="json")
    assert res.status_code == 201
    profile = HealthProfile.objects.get(user=user)
    assert (profile.status, profile.completion_percent) == ("active", 0)
    user.refresh_from_db()
    assert user.role == "user"


@pytest.mark.django_db
def test_user_only_sees_own_profile_and_no_route_to_others(client, user, other_user):
    make_profile(user, full_name="Momina Asif")
    other = make_profile(other_user, full_name="Bilal Ahmed")
    user_login(client)
    assert client.get(ROOT).data["demographics"]["full_name"] == "Momina Asif"
    # No route takes a profile id, so another member's profile cannot be asked for.
    assert client.get(f"/api/profiles/{other.id}/").status_code == 404
    assert client.get(f"{ROOT}?id={other.id}").data["demographics"]["full_name"] == "Momina Asif"


@pytest.mark.django_db
def test_delete_profile_removes_sections_but_keeps_the_account(client, user, profile):
    user_login(client)
    assert client.delete(ROOT).status_code == 204
    assert not HealthProfile.objects.filter(user=user).exists()
    assert client.get(ROOT).status_code == 404
    # the account still works: sign in again and create a new profile
    fresh = type(client)()
    assert user_login(fresh).status_code == 200
    assert fresh.post(ROOT, format="json").status_code == 201


# ------------------------------------------------------------------ deactivated profile = read-only
@pytest.mark.django_db
def test_deactivated_profile_can_be_read(client, user):
    make_profile(user, status="deactivated")
    user_login(client)
    for url in (ROOT, ROOT + "demographics/", ROOT + "wellness/", ROOT + "emergency-contacts/", ROOT + "activity/"):
        assert client.get(url).status_code == 200, url


@pytest.mark.django_db
@pytest.mark.parametrize(
    "method,url,body",
    [
        ("put", ROOT + "demographics/", DEMO),
        ("patch", ROOT + "demographics/", {"city": "Karachi"}),
        ("put", ROOT + "wellness/", WELLNESS),
        ("patch", ROOT + "wellness/", {"allergies": "Dust"}),
        ("post", ROOT + "emergency-contacts/", CONTACT),
        ("delete", ROOT, None),
    ],
)
def test_deactivated_profile_rejects_every_write_with_403_and_audits_it(client, user, method, url, body):
    make_profile(user, status="deactivated")
    user_login(client)
    before = AuditEvent.objects.filter(outcome="denied").count()
    assert getattr(client, method)(url, body, format="json").status_code == 403
    assert AuditEvent.objects.filter(outcome="denied").count() == before + 1
    assert HealthProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_deactivated_profile_cannot_change_or_delete_a_contact(client, user):
    profile = make_profile(user, status="deactivated")
    contact = profile.emergency_contacts.get()
    user_login(client)
    assert client.patch(f"{ROOT}emergency-contacts/{contact.id}/", {"name": "New Name"}, format="json").status_code == 403
    assert client.delete(f"{ROOT}emergency-contacts/{contact.id}/").status_code == 403
    assert profile.emergency_contacts.count() == 1


# ------------------------------------------------------------------ CSRF on every write
@pytest.mark.django_db
@pytest.mark.parametrize(
    "method,url,body",
    [
        ("post", ROOT, None),
        ("delete", ROOT, None),
        ("put", ROOT + "demographics/", DEMO),
        ("patch", ROOT + "demographics/", {"city": "X Town"}),
        ("put", ROOT + "wellness/", WELLNESS),
        ("patch", ROOT + "wellness/", {"goals": []}),
        ("post", ROOT + "emergency-contacts/", CONTACT),
        ("patch", ROOT + "emergency-contacts/1/", {"name": "New Name"}),
        ("delete", ROOT + "emergency-contacts/1/", None),
    ],
)
def test_every_member_write_without_csrf_header_is_403(csrf_client, user, profile, method, url, body):
    csrf_header(csrf_client)
    assert csrf_client.post(
        "/api/auth/user/login/", {"email": "momina@example.com", "password": "CalmMorning2026"}, format="json"
    ).status_code == 200
    res = getattr(csrf_client, method)(url, body, format="json")  # no X-CSRFToken header
    assert res.status_code == 403
    assert "CSRF" in res.json()["error"]["message"]
