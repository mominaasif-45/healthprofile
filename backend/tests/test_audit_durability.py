"""
Audit durability: a write and its REQUIRED audit event commit together or not at all.

Each test makes the audit insert fail, sends a real API request, then checks that:
  - the response is 503 with the usual error shape and code "audit_unavailable",
  - the data (and the stored completion numbers) did not change,
  - no audit row was written.

transaction=True: the test database is not wrapped in one big test transaction, so these
tests see real COMMIT / ROLLBACK behaviour, the same as production.
"""
import pytest
from django.db import DatabaseError

from audit.models import AuditEvent
from profiles.models import Demographics, EmergencyContact, HealthProfile, WellnessGoal, WellnessPreference

from .conftest import admin_login, make_profile, user_login

ROOT = "/api/profiles/me/"
DURABLE = pytest.mark.django_db(transaction=True)

real_create = AuditEvent.objects.create


def fail_audit(monkeypatch):
    """Every audit insert raises, as if the database refused it."""
    def boom(**kwargs):
        raise DatabaseError("audit table unavailable")

    monkeypatch.setattr(AuditEvent.objects, "create", boom)


def assert_audit_failed(res):
    assert res.status_code == 503
    assert res.data["error"]["code"] == "audit_unavailable"
    assert set(res.data["error"]) >= {"code", "message", "fields"}
    assert AuditEvent.objects.count() == 0


def snapshot(profile):
    """Everything a member write could change, read fresh from the database."""
    profile = HealthProfile.objects.get(pk=profile.pk)
    return {
        "completion": (profile.completion_percent, profile.completion_status),
        "status": profile.status,
        "demographics": list(Demographics.objects.filter(profile=profile).values()),
        "contacts": list(EmergencyContact.objects.filter(profile=profile).order_by("id").values()),
        "wellness": list(WellnessPreference.objects.filter(profile=profile).values()),
        "goals": sorted(WellnessGoal.objects.filter(preference__profile=profile).values_list("goal", flat=True)),
    }


@pytest.fixture
def me(client, user):
    user_login(client)
    return client


@pytest.fixture
def half_profile(user):
    """Demographics + one contact = 50%, so adding a section would visibly change completion."""
    profile = make_profile(user, sections=("demographics", "contact"))
    AuditEvent.objects.all()._raw_delete(AuditEvent.objects.db)
    return profile


# ------------------------------------------------------------------ member section writes
@DURABLE
@pytest.mark.parametrize(
    "method, path, body",
    [
        ("put", "demographics/", {"full_name": "New Name", "age_range": "35-44", "city": "Karachi"}),
        ("patch", "demographics/", {"city": "Karachi"}),
        ("put", "wellness/", {"contact_preference": "sms", "goals": ["hydration"]}),  # would make it 100%
        ("post", "emergency-contacts/", {"name": "Bilal Ahmed", "relationship": "sibling", "phone": "+92 311 1112223"}),
    ],
)
def test_failed_audit_rolls_back_section_write_and_completion(me, half_profile, monkeypatch, method, path, body):
    before = snapshot(half_profile)
    fail_audit(monkeypatch)

    res = getattr(me, method)(ROOT + path, body, format="json")

    assert_audit_failed(res)
    assert snapshot(half_profile) == before


@DURABLE
def test_failed_audit_rolls_back_contact_update(me, half_profile, monkeypatch):
    contact = EmergencyContact.objects.get(profile=half_profile)
    before = snapshot(half_profile)
    fail_audit(monkeypatch)

    res = me.patch(f"{ROOT}emergency-contacts/{contact.id}/", {"relationship": "parent"}, format="json")

    assert_audit_failed(res)
    assert snapshot(half_profile) == before


@DURABLE
def test_failed_audit_rolls_back_contact_delete_and_primary_promotion(me, half_profile, monkeypatch):
    first = EmergencyContact.objects.get(profile=half_profile)
    EmergencyContact.objects.create(profile=half_profile, name="Ali Raza", relationship="friend", phone="+923224445556")
    before = snapshot(half_profile)
    fail_audit(monkeypatch)

    res = me.delete(f"{ROOT}emergency-contacts/{first.id}/")

    assert_audit_failed(res)
    after = snapshot(half_profile)
    assert after == before  # the primary still exists and nobody was promoted
    assert [c["is_primary"] for c in after["contacts"]] == [True, False]


# ------------------------------------------------------------------ root profile
@DURABLE
def test_failed_audit_rolls_back_profile_creation(me, user, monkeypatch):
    fail_audit(monkeypatch)

    res = me.post(ROOT, format="json")

    assert_audit_failed(res)
    assert not HealthProfile.objects.filter(user=user).exists()


@DURABLE
def test_failed_audit_rolls_back_profile_deletion_completely(me, user, monkeypatch):
    profile = make_profile(user)  # all four sections, 100%
    AuditEvent.objects.all()._raw_delete(AuditEvent.objects.db)
    before = snapshot(profile)
    fail_audit(monkeypatch)

    res = me.delete(ROOT)

    assert_audit_failed(res)
    assert HealthProfile.objects.filter(pk=profile.pk).exists()
    assert snapshot(profile) == before  # every section and the stored completion survived the cascade attempt


@DURABLE
def test_real_database_error_in_audit_insert_rolls_back(me, half_profile, monkeypatch):
    """Not a Python exception: PostgreSQL itself rejects the audit row (action longer than 40 chars)."""
    before = snapshot(half_profile)
    monkeypatch.setattr(AuditEvent.objects, "create", lambda **kw: real_create(**{**kw, "action": "x" * 60}))

    res = me.patch(ROOT + "demographics/", {"city": "Karachi"}, format="json")

    assert_audit_failed(res)
    assert snapshot(half_profile) == before


# ------------------------------------------------------------------ admin status changes
@DURABLE
@pytest.mark.parametrize("start, action, path", [
    ("active", "deactivate", "deactivate/"),
    ("deactivated", "reactivate", "reactivate/"),
])
def test_failed_audit_rolls_back_admin_status_change(client, admin, other_user, monkeypatch, start, action, path):
    profile = make_profile(other_user, status=start)
    admin_login(client)
    AuditEvent.objects.all()._raw_delete(AuditEvent.objects.db)
    fail_audit(monkeypatch)

    res = client.post(f"/api/admin/profiles/{profile.id}/{path}")

    assert_audit_failed(res)
    profile.refresh_from_db()
    assert profile.status == start


# ------------------------------------------------------------------ the helper itself
@DURABLE
def test_record_event_refuses_to_run_outside_a_transaction(user):
    from audit.services import record_event

    with pytest.raises(RuntimeError):
        record_event(None, "profile.created", actor=user)
    assert AuditEvent.objects.count() == 0


@DURABLE
def test_record_event_raises_audit_unavailable_on_failure(user, monkeypatch):
    from django.db import transaction

    from audit.services import AuditUnavailable, record_event

    fail_audit(monkeypatch)
    with pytest.raises(AuditUnavailable), transaction.atomic():
        record_event(None, "profile.created", actor=user)
