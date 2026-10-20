"""Phase 3: admins never see sensitive fields, and no response anywhere leaks secrets."""
import json

import pytest

from .conftest import admin_login, make_profile, user_login

LIST = "/api/admin/profiles/"
# keys that must never appear in ANY JSON response, however deeply nested
FORBIDDEN_KEYS = {
    "password", "password_hash", "is_superuser", "is_staff", "last_login", "access", "refresh", "token",
    "sessionid", "session_key", "csrfmiddlewaretoken",
}
ADMIN_HIDDEN = {"date_of_birth", "allergies", "lifestyle_notes", "phone"}


def all_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from all_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from all_keys(item)


@pytest.mark.django_db
def test_admin_detail_hides_sensitive_fields_and_masks_phones(client, admin, user, profile):
    admin_login(client)
    detail = client.get(f"{LIST}{profile.id}/").data

    keys = set(all_keys(detail))
    assert not (keys & ADMIN_HIDDEN), keys & ADMIN_HIDDEN  # date_of_birth, allergies, lifestyle_notes, phone: absent
    assert "date_of_birth" not in detail["demographics"]
    assert "allergies" not in detail["wellness"] and "lifestyle_notes" not in detail["wellness"]
    assert detail["wellness"]["has_allergies"] is True  # a yes/no only
    assert detail["demographics"]["age_range"] == "25-34"

    contact = detail["emergency_contacts"][0]
    assert contact["phone_masked"] == "•••• •••• 4567"
    text = json.dumps(detail, ensure_ascii=False)
    for secret in ("+92 300 1234567", "300 1234", "Peanuts", "Secret note", "1995-06-15"):
        assert secret not in text, secret


@pytest.mark.django_db
def test_age_range_is_derived_from_date_of_birth_without_exposing_it(client, admin, user):
    profile = make_profile(user, sections=("demographics",))
    profile.demographics.age_range = None
    profile.demographics.date_of_birth = "1995-06-15"
    profile.demographics.save()
    admin_login(client)
    demographics = client.get(f"{LIST}{profile.id}/").data["demographics"]
    assert demographics["age_range"] == "25-34" and "date_of_birth" not in demographics


@pytest.mark.django_db
def test_has_allergies_is_false_when_empty(client, admin, user):
    profile = make_profile(user)
    profile.wellness.allergies = "   "
    profile.wellness.save()
    admin_login(client)
    assert client.get(f"{LIST}{profile.id}/").data["wellness"]["has_allergies"] is False


@pytest.mark.django_db
def test_member_still_sees_their_own_full_data(client, user, profile):
    user_login(client)
    data = client.get("/api/profiles/me/").data
    assert data["wellness"]["allergies"] == "Peanuts" and data["wellness"]["lifestyle_notes"] == "Secret note"
    assert data["demographics"]["date_of_birth"] == "1995-06-15"
    assert data["emergency_contacts"][0]["phone"] == "+92 300 1234567"


@pytest.mark.django_db
def test_no_response_contains_a_forbidden_key(client, admin, user, profile):
    member = type(client)()
    user_login(member)
    seen = [member.get(url).json() for url in (
        "/api/auth/me/", "/api/profiles/me/", "/api/profiles/me/demographics/", "/api/profiles/me/wellness/",
        "/api/profiles/me/emergency-contacts/", "/api/profiles/me/activity/",
    )]
    admin_login(client)
    seen += [client.get(url).json() for url in (
        "/api/admin/me/", LIST, f"{LIST}{profile.id}/", f"{LIST}{profile.id}/audit-events/", "/api/admin/audit-events/",
    )]
    for body in seen:
        assert not (set(all_keys(body)) & FORBIDDEN_KEYS), body


@pytest.mark.django_db
def test_login_response_has_no_token_or_hash(client, user):
    res = user_login(client)
    assert not (set(all_keys(res.json())) & FORBIDDEN_KEYS)
    assert "pbkdf2" not in res.content.decode() and "md5$" not in res.content.decode()
