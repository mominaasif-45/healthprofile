"""Phase 2: audit events (member side), request ids and the append-only guarantee."""
import json
import uuid

import pytest

from accounts.models import User
from audit.models import AppendOnlyError, AuditEvent
from audit.services import log_event

from .conftest import PASSWORD, make_profile, user_login

ROOT = "/api/profiles/me/"
SECRET_PHONE = "+92 311 9876543"
SECRET_ALLERGY = "Zebra-Dander-Allergy"
SECRET_NOTE = "My-Very-Private-Note"


@pytest.fixture
def me(client, user):
    user_login(client)
    return client


def events():
    return list(AuditEvent.objects.order_by("id"))


# ------------------------------------------------------------------ one event per write
@pytest.mark.django_db
@pytest.mark.parametrize(
    "method, url, body, action, fields",
    [
        ("post", ROOT, None, "profile.created", []),
        ("put", ROOT + "demographics/", {"full_name": "Momina Asif", "age_range": "25-34", "city": "Lahore"},
         "demographics.updated", ["age_range", "city", "date_of_birth", "full_name", "gender", "preferred_name"]),
        ("put", ROOT + "wellness/", {"contact_preference": "sms", "goals": ["hydration"]},
         "wellness.updated", ["activity_level", "allergies", "contact_preference", "diet_preference",
                              "goals", "lifestyle_notes", "sleep_goal_hours"]),
        ("post", ROOT + "emergency-contacts/", {"name": "Bilal Ahmed", "relationship": "sibling", "phone": SECRET_PHONE},
         "emergency_contact.created", ["name", "phone", "relationship"]),
    ],
)
def test_each_member_write_creates_exactly_one_correct_event(me, user, method, url, body, action, fields):
    if method != "post" or url != ROOT:
        me.post(ROOT, format="json")
    AuditEvent.objects.all()._raw_delete(AuditEvent.objects.db)  # start from a clean log for the one write under test
    res = getattr(me, method)(url, body, format="json")
    assert res.status_code in (200, 201)

    [event] = events()
    assert event.action == action
    assert event.actor_id == user.id and event.actor_role == "user"
    assert (event.target_type, event.outcome) == ("health_profile", "success")
    assert event.target_id == user.health_profile.id
    assert event.changed_fields == fields
    assert str(event.request_id) == res["X-Request-ID"]


@pytest.mark.django_db
def test_patch_and_delete_events_name_only_the_changed_fields(me, user, profile):
    contact = profile.emergency_contacts.get()
    AuditEvent.objects.all()._raw_delete(AuditEvent.objects.db)

    me.patch(ROOT + "demographics/", {"city": "Karachi"}, format="json")
    me.patch(ROOT + "wellness/", {"goals": ["hydration"]}, format="json")  # only goals -> goals.updated
    me.patch(f"{ROOT}emergency-contacts/{contact.id}/", {"relationship": "parent"}, format="json")
    me.delete(f"{ROOT}emergency-contacts/{contact.id}/")
    me.delete(ROOT)

    got = [(e.action, e.changed_fields) for e in events()]
    assert got == [
        ("demographics.updated", ["city"]),
        ("goals.updated", ["goals"]),
        ("emergency_contact.updated", ["relationship"]),
        ("emergency_contact.deleted", []),
        ("profile.deleted", []),
    ]
    assert events()[-1].target_id == profile.id  # the history keeps pointing at the deleted profile


@pytest.mark.django_db
def test_failed_validation_creates_no_event(me, empty_profile):
    AuditEvent.objects.all()._raw_delete(AuditEvent.objects.db)
    assert me.put(ROOT + "demographics/", {"full_name": "M"}, format="json").status_code == 400
    assert events() == []


# ------------------------------------------------------------------ nothing sensitive is stored
@pytest.mark.django_db
def test_no_audit_field_contains_secrets_or_values(client, user, other_user):
    make_profile(other_user)
    res = user_login(client)
    assert res.status_code == 200
    access, refresh = client.cookies["access"].value, client.cookies["refresh"].value
    csrf = client.get("/api/csrf/").cookies  # noqa: F841 - make sure a csrftoken exists
    session_like = client.cookies["csrftoken"].value

    client.post(ROOT, format="json")
    client.put(ROOT + "demographics/", {"full_name": "Momina Asif", "date_of_birth": "1995-06-15", "city": "Lahore"}, format="json")
    client.put(ROOT + "wellness/", {"contact_preference": "email", "allergies": SECRET_ALLERGY,
                                   "lifestyle_notes": SECRET_NOTE, "goals": ["hydration"]}, format="json")
    client.post(ROOT + "emergency-contacts/", {"name": "Bilal Ahmed", "relationship": "sibling", "phone": SECRET_PHONE}, format="json")
    client.get("/api/admin/profiles/?search=a-secret-search-term")  # 403, but must not be logged either

    dump = json.dumps(
        list(AuditEvent.objects.values()), default=str
    ).lower()
    for secret in (PASSWORD, access, refresh, session_like, SECRET_PHONE, "9876543", SECRET_ALLERGY, SECRET_NOTE,
                   "1995-06-15", "lahore", "bilal ahmed", "momina@example.com", "a-secret-search-term", "127.0.0.1"):
        assert secret.lower() not in dump, f"{secret!r} leaked into the audit log"


@pytest.mark.django_db
def test_log_event_accepts_only_plain_field_names():
    log_event(None, "profile.updated", changed_fields=["city", SECRET_PHONE, "a@b.com", "x" * 80, "Full Name", 42, "city"])
    [event] = events()
    assert event.changed_fields == ["city"]  # values, emails, long strings, spaces, numbers are dropped


@pytest.mark.django_db
def test_log_event_never_raises_into_the_request(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(AuditEvent.objects, "create", boom)
    log_event(None, "profile.created")  # must not raise


# ------------------------------------------------------------------ append-only
@pytest.mark.django_db
def test_audit_events_cannot_be_updated_or_deleted_through_the_orm(user):
    log_event(None, "profile.created", actor=user)
    event = AuditEvent.objects.get()
    event.outcome = "failed"
    with pytest.raises(AppendOnlyError):
        event.save()
    with pytest.raises(AppendOnlyError):
        event.delete()
    with pytest.raises(AppendOnlyError):
        AuditEvent.objects.all().update(outcome="failed")
    with pytest.raises(AppendOnlyError):
        AuditEvent.objects.all().delete()
    assert AuditEvent.objects.get().outcome == "success"


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_no_api_route_can_change_audit_events(client, admin, method):
    from .conftest import admin_login

    admin_login(client)
    assert getattr(client, method)("/api/admin/audit-events/", {}, format="json").status_code == 405
    assert getattr(client, method)("/api/admin/audit-events/1/", {}, format="json").status_code == 404
    assert getattr(client, method)(ROOT + "activity/", {}, format="json").status_code in (401, 403, 405)


@pytest.mark.django_db
def test_history_survives_deleting_the_user(user):
    log_event(None, "profile.created", actor=user)
    user.delete()
    event = AuditEvent.objects.get()
    assert event.actor is None and event.actor_role == "user"


# ------------------------------------------------------------------ request id
@pytest.mark.django_db
def test_every_response_has_a_request_id(client, user):
    assert uuid.UUID(client.get("/api/health/")["X-Request-ID"])
    assert uuid.UUID(client.get(ROOT)["X-Request-ID"])  # even a 401


@pytest.mark.django_db
def test_valid_incoming_request_id_is_kept_and_invalid_is_replaced(client):
    mine = str(uuid.uuid4())
    assert client.get("/api/health/", HTTP_X_REQUEST_ID=mine)["X-Request-ID"] == mine
    bad = client.get("/api/health/", HTTP_X_REQUEST_ID="not-a-uuid; DROP TABLE")["X-Request-ID"]
    assert bad != "not-a-uuid; DROP TABLE" and uuid.UUID(bad)


@pytest.mark.django_db
def test_error_body_carries_the_request_id_and_audit_row_matches(me, user):
    mine = str(uuid.uuid4())
    res = me.put(ROOT + "demographics/", {"full_name": "M"}, format="json", HTTP_X_REQUEST_ID=mine)
    assert res.status_code == 404 or res.status_code == 400
    assert res.json()["error"]["request_id"] == mine == res["X-Request-ID"]

    me.post(ROOT, format="json", HTTP_X_REQUEST_ID=mine)
    assert str(AuditEvent.objects.get(action="profile.created").request_id) == mine


# ------------------------------------------------------------------ member activity endpoint
@pytest.mark.django_db
def test_activity_shows_only_my_events_newest_first(client, user, other_user):
    other = type(client)()
    user_login(other, email="bilal@example.com")
    other.post(ROOT, format="json")

    user_login(client)
    client.post(ROOT, format="json")
    client.put(ROOT + "demographics/", {"full_name": "Momina Asif", "age_range": "25-34"}, format="json")

    res = client.get(ROOT + "activity/")
    assert res.status_code == 200
    assert [e["action"] for e in res.data["results"]] == ["demographics.updated", "profile.created"]
    assert all(e["target_id"] == user.health_profile.id for e in res.data["results"])
    assert "actor" not in res.data["results"][0]


@pytest.mark.django_db
def test_activity_is_paginated(me, user):
    me.post(ROOT, format="json")
    for n in range(12):
        me.put(ROOT + "demographics/", {"full_name": f"Momina {n:02d}", "age_range": "25-34"}, format="json")
    page1 = me.get(ROOT + "activity/").data
    assert page1["count"] == 13 and len(page1["results"]) == 10 and page1["next"]
    assert len(me.get(ROOT + "activity/?page=2").data["results"]) == 3


@pytest.mark.django_db
def test_users_model_has_no_audit_back_relation_leak(user):
    assert not hasattr(User, "auditevent_set")  # related_name="+": no accidental reverse accessor
