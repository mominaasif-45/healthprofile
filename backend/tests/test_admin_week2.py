"""Phase 3: admin filtering, ordering, reactivate, audit endpoints, throttling and role boundaries."""
import datetime as dt

import pytest
from django.utils import timezone

from accounts.models import User
from audit.models import AuditEvent
from profiles.models import HealthProfile

from .conftest import PASSWORD, admin_login, csrf_header, make_profile, user_login
from .test_profiles import ALL_MEMBER_ROUTES

LIST = "/api/admin/profiles/"

# every admin URL that needs a signed-in admin (login is public by design, so it is not here)
ADMIN_ROUTES = [
    ("get", "/api/admin/me/"), ("post", "/api/admin/logout/"),
    ("get", LIST), ("get", f"{LIST}1/"),
    ("post", f"{LIST}1/deactivate/"), ("post", f"{LIST}1/reactivate/"),
    ("get", f"{LIST}1/audit-events/"), ("get", "/api/admin/audit-events/"),
]


@pytest.fixture
def adm(client, admin):
    admin_login(client)
    return client


def seed_members(n=3):
    """n members with different completion levels and creation dates."""
    levels = [("demographics",), ("demographics", "contact", "wellness"), ("demographics", "contact", "wellness", "goal")]
    out = []
    for i in range(n):
        u = User.objects.create_user(email=f"member{i}@example.com", password=PASSWORD, name=f"Member {i}")
        p = make_profile(u, full_name=f"Member Number{i}", sections=levels[i % 3])
        HealthProfile.objects.filter(pk=p.pk).update(created_at=timezone.now() - dt.timedelta(days=10 - i * 3))
        out.append(p)
    return out


# ------------------------------------------------------------------ role boundaries
@pytest.mark.django_db
@pytest.mark.parametrize("method,url", ADMIN_ROUTES)
def test_member_jwt_gets_403_on_every_admin_route(client, user, profile, method, url):
    user_login(client)
    assert getattr(client, method)(url).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("method,url", ADMIN_ROUTES)
def test_signed_out_gets_403_on_every_admin_route(client, method, url):
    assert getattr(client, method)(url).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("method,url,body", ALL_MEMBER_ROUTES)
def test_admin_session_alone_cannot_use_member_routes(adm, method, url, body):
    assert getattr(adm, method)(url, body, format="json").status_code in (401, 403)


# ------------------------------------------------------------------ filters, ordering, pagination
@pytest.mark.django_db
def test_list_returns_only_the_allowed_fields(adm):
    seed_members(1)
    row = adm.get(LIST).data["results"][0]
    assert set(row) == {"id", "display_name", "email", "status", "completion_status", "completion_percent", "created_at"}


@pytest.mark.django_db
def test_filter_by_completion_status(adm):
    seed_members(3)
    assert adm.get(LIST + "?completion_status=complete").data["count"] == 1
    assert adm.get(LIST + "?completion_status=in_progress").data["count"] == 2
    assert adm.get(LIST + "?completion_status=not_started").data["count"] == 0


@pytest.mark.django_db
def test_filter_by_created_date_range(adm):
    seed_members(3)  # created 10, 7 and 4 days ago
    day = lambda d: (timezone.localdate() - dt.timedelta(days=d)).isoformat()  # noqa: E731
    assert adm.get(f"{LIST}?created_after={day(8)}").data["count"] == 2
    assert adm.get(f"{LIST}?created_before={day(8)}").data["count"] == 1
    assert adm.get(f"{LIST}?created_after={day(8)}&created_before={day(5)}").data["count"] == 1


@pytest.mark.django_db
def test_filters_combine(adm):
    seed_members(3)
    res = adm.get(LIST + "?search=member&status=active&completion_status=in_progress&ordering=completion_percent")
    assert res.status_code == 200
    assert [r["completion_percent"] for r in res.data["results"]] == [25, 75]


@pytest.mark.django_db
def test_search_matches_name_preferred_name_and_email_case_insensitively(adm, user):
    p = make_profile(user, full_name="Momina Asif")
    p.demographics.preferred_name = "Moni"
    p.demographics.save()
    for term in ("MOMINA", "moni", "momina@exa"):
        assert [r["id"] for r in adm.get(f"{LIST}?search={term}").data["results"]] == [p.id], term
    assert adm.get(LIST + "?search=nobody-here").data["count"] == 0


@pytest.mark.django_db
def test_ordering_options(adm):
    seed_members(3)
    pcts = lambda o: [r["completion_percent"] for r in adm.get(f"{LIST}?ordering={o}").data["results"]]  # noqa: E731
    assert pcts("completion_percent") == [25, 75, 100]
    assert pcts("-completion_percent") == [100, 75, 25]
    ids = lambda o: [r["id"] for r in adm.get(f"{LIST}?ordering={o}").data["results"]]  # noqa: E731
    assert ids("created_at") == sorted(ids("created_at")) and ids("-created_at") == ids("created_at")[::-1]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "query, field",
    [
        ("status=bogus", "status"), ("completion_status=halfway", "completion_status"),
        ("created_after=yesterday", "created_after"), ("created_before=2026-13-45", "created_before"),
        ("ordering=email", "ordering"), ("ordering=-password", "ordering"),
        ("created_after=2026-10-10&created_before=2026-01-01", "created_after"),
        ("search=" + "x" * 101, "search"),
    ],
)
def test_invalid_filter_values_return_400_with_field_errors(adm, query, field):
    res = adm.get(f"{LIST}?{query}")
    assert res.status_code == 400 and field in res.json()["error"]["fields"]


@pytest.mark.django_db
def test_list_is_paginated_and_stable(adm):
    for i in range(23):
        u = User.objects.create_user(email=f"p{i}@example.com", password=PASSWORD, name=f"P {i}")
        make_profile(u, sections=())
    pages = [adm.get(f"{LIST}?page={n}").data for n in (1, 2, 3)]
    assert [len(p["results"]) for p in pages] == [10, 10, 3] and pages[0]["count"] == 23
    seen = [r["id"] for p in pages for r in p["results"]]
    assert len(set(seen)) == 23  # no row repeated or skipped across pages


# ------------------------------------------------------------------ deactivate / reactivate
@pytest.mark.django_db
def test_deactivate_and_reactivate_need_csrf_and_are_audited(csrf_client, admin, user, profile):
    headers = csrf_header(csrf_client)
    assert csrf_client.post("/api/admin/login/", {"email": "admin@example.com", "password": PASSWORD},
                            format="json", **headers).status_code == 200
    headers = csrf_header(csrf_client)  # the token rotates at login
    for action in ("deactivate", "reactivate"):
        url = f"{LIST}{profile.id}/{action}/"
        assert csrf_client.post(url).status_code == 403  # no CSRF header
    profile.refresh_from_db()
    assert profile.status == "active"

    res = csrf_client.post(f"{LIST}{profile.id}/deactivate/", **headers)
    assert res.status_code == 200 and res.data["status"] == "deactivated"
    res = csrf_client.post(f"{LIST}{profile.id}/reactivate/", **headers)
    assert res.status_code == 200 and res.data["status"] == "active"

    actions = list(
        AuditEvent.objects.filter(action__startswith="admin.profile_").order_by("id").values_list("action", "changed_fields")
    )
    assert actions == [("admin.profile_deactivated", ["status"]), ("admin.profile_reactivated", ["status"])]


@pytest.mark.django_db
def test_reactivating_lets_the_owner_edit_again(adm, user, profile):
    owner = type(adm)()
    user_login(owner)
    adm.post(f"{LIST}{profile.id}/deactivate/")
    assert owner.patch("/api/profiles/me/demographics/", {"city": "Karachi"}, format="json").status_code == 403
    adm.post(f"{LIST}{profile.id}/reactivate/")
    assert owner.patch("/api/profiles/me/demographics/", {"city": "Karachi"}, format="json").status_code == 200


@pytest.mark.django_db
def test_status_change_on_unknown_profile_is_404(adm):
    assert adm.post(f"{LIST}999999/deactivate/").status_code == 404
    assert adm.post(f"{LIST}999999/reactivate/").status_code == 404


@pytest.mark.django_db
def test_repeating_a_status_change_is_harmless_and_records_no_changed_field(adm, profile):
    adm.post(f"{LIST}{profile.id}/reactivate/")  # already active
    event = AuditEvent.objects.get(action="admin.profile_reactivated")
    assert event.changed_fields == []


# ------------------------------------------------------------------ audit of admin actions
@pytest.mark.django_db
def test_admin_login_logout_and_view_are_audited(client, admin, profile):
    admin_login(client)
    client.get(f"{LIST}{profile.id}/")
    client.post("/api/admin/logout/")
    rows = list(AuditEvent.objects.order_by("id").values_list("action", "actor_role", "outcome", "target_id"))
    assert rows == [
        ("admin.login", "admin", "success", None),
        ("admin.profile_viewed", "admin", "success", profile.id),
        ("admin.logout", "admin", "success", None),
    ]


@pytest.mark.django_db
def test_failed_admin_login_is_audited_without_the_email(client, admin, user):
    admin_login(client, email="admin@example.com", password="WrongPassword123")
    admin_login(client, email="momina@example.com")  # a member trying the admin door
    failed, denied = AuditEvent.objects.order_by("id")
    assert (failed.action, failed.outcome, failed.actor_id, failed.actor_role) == ("admin.login_failed", "failed", None, "anonymous")
    assert (denied.action, denied.outcome, denied.actor_role) == ("admin.login_failed", "denied", "user")
    dump = str(list(AuditEvent.objects.values())).lower()
    assert "admin@example.com" not in dump and "wrongpassword" not in dump


@pytest.mark.django_db
def test_admin_login_is_throttled_after_five_attempts(client, admin):
    codes = [admin_login(client, password="WrongPassword123").status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


# ------------------------------------------------------------------ audit endpoints
@pytest.mark.django_db
def test_profile_history_lists_member_and_admin_actions_newest_first(adm, user, profile):
    owner = type(adm)()
    user_login(owner)
    owner.patch("/api/profiles/me/demographics/", {"city": "Karachi"}, format="json")
    adm.get(f"{LIST}{profile.id}/")
    res = adm.get(f"{LIST}{profile.id}/audit-events/")
    assert res.status_code == 200
    assert [e["action"] for e in res.data["results"]] == ["admin.profile_viewed", "demographics.updated"]
    assert adm.get(f"{LIST}999999/audit-events/").status_code == 404


@pytest.mark.django_db
def test_global_audit_list_filters(adm, user, profile):
    owner = type(adm)()
    user_login(owner)
    owner.patch("/api/profiles/me/demographics/", {"city": "Karachi"}, format="json")
    owner.patch("/api/profiles/me/demographics/", {"city": "Lahore"}, format="json")
    url = "/api/admin/audit-events/"
    assert adm.get(f"{url}?action=demographics.updated").data["count"] == 2
    assert adm.get(f"{url}?actor={user.id}").data["count"] == 2
    assert adm.get(f"{url}?outcome=denied").data["count"] == 0
    today = timezone.localdate().isoformat()
    assert adm.get(f"{url}?created_after={today}&created_before={today}").data["count"] >= 2
    assert adm.get(f"{url}?created_after=2999-01-01").data["count"] == 0


@pytest.mark.django_db
@pytest.mark.parametrize("query", ["action=nope", "outcome=maybe", "actor=abc", "actor=0", "created_after=soon"])
def test_global_audit_invalid_filters_return_400(adm, query):
    assert adm.get(f"/api/admin/audit-events/?{query}").status_code == 400


@pytest.mark.django_db
def test_audit_events_show_the_actor_as_an_id_only(adm, user, profile):
    owner = type(adm)()
    user_login(owner)
    owner.patch("/api/profiles/me/demographics/", {"city": "Karachi"}, format="json")
    event = adm.get(f"/api/admin/audit-events/?action=demographics.updated").data["results"][0]
    assert event["actor"] == user.id
    assert "momina@example.com" not in str(event) and set(event) == {
        "id", "created_at", "actor", "actor_role", "action", "target_type", "target_id",
        "changed_fields", "outcome", "request_id",
    }
