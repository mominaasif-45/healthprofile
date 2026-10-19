import pytest
from django.contrib.sessions.models import Session

from profiles.models import HealthProfile

from .conftest import PASSWORD, admin_login, csrf_header, make_profile, user_login


@pytest.mark.django_db
def test_normal_user_jwt_gets_403_on_admin_routes(client, user, profile):
    user_login(client)
    assert client.get("/api/admin/profiles/").status_code == 403
    assert client.get("/api/admin/me/").status_code == 403
    assert client.get(f"/api/admin/profiles/{profile.id}/").status_code == 403


@pytest.mark.django_db
def test_not_logged_in_cannot_reach_admin_routes(client, profile):
    assert client.get("/api/admin/profiles/").status_code == 403


@pytest.mark.django_db
def test_non_admin_credentials_cannot_start_admin_session(client, user):
    res = admin_login(client, email="ayesha@example.com")
    assert res.status_code == 403
    assert "sessionid" not in res.cookies


@pytest.mark.django_db
def test_wrong_admin_password_returns_401(client, admin):
    assert admin_login(client, password="WrongPassword123").status_code == 401


@pytest.mark.django_db
def test_admin_session_cookie_is_httponly_and_not_a_user_token(client, admin):
    res = admin_login(client)
    assert res.status_code == 200
    assert res.cookies["sessionid"]["httponly"]
    assert "access" not in res.cookies and "refresh" not in res.cookies
    # an admin session does not work on user (JWT) routes
    assert client.get("/api/auth/me/").status_code == 401
    assert client.get("/api/profiles/me/").status_code == 401


@pytest.mark.django_db
def test_admin_session_can_list_search_and_view_detail(client, admin, user, other_user):
    make_profile(user, full_name="Ayesha Khan")
    bilal = make_profile(other_user, full_name="Bilal Ahmed")
    admin_login(client)

    listing = client.get("/api/admin/profiles/")
    assert listing.status_code == 200
    assert listing.data["count"] == 2

    by_name = client.get("/api/admin/profiles/?search=ayesha")
    assert [r["full_name"] for r in by_name.data["results"]] == ["Ayesha Khan"]

    by_email = client.get("/api/admin/profiles/?search=bilal@")
    assert [r["full_name"] for r in by_email.data["results"]] == ["Bilal Ahmed"]

    detail = client.get(f"/api/admin/profiles/{bilal.id}/")
    assert detail.status_code == 200
    assert detail.data["email"] == "bilal@example.com"
    assert client.get("/api/admin/profiles/999999/").status_code == 404


@pytest.mark.django_db
def test_status_filter_and_bad_status(client, admin, user, other_user):
    make_profile(user)
    make_profile(other_user, status="deactivated")
    admin_login(client)
    assert client.get("/api/admin/profiles/?status=active").data["count"] == 1
    assert client.get("/api/admin/profiles/?status=deactivated").data["count"] == 1
    assert client.get("/api/admin/profiles/?status=bogus").status_code == 400


@pytest.mark.django_db
def test_list_is_paginated_newest_first(client, admin, db):
    from accounts.models import User

    for i in range(12):
        u = User.objects.create_user(email=f"m{i}@example.com", password=PASSWORD, name=f"Member {i}")
        make_profile(u)
    admin_login(client)
    page1 = client.get("/api/admin/profiles/")
    page2 = client.get("/api/admin/profiles/?page=2")
    assert page1.data["count"] == 12
    assert len(page1.data["results"]) == 10 and len(page2.data["results"]) == 2
    assert page1.data["results"][0]["full_name"] == "Member 11"


@pytest.mark.django_db
def test_deactivate_without_csrf_token_returns_403(csrf_client, admin, profile):
    headers = csrf_header(csrf_client)
    assert admin_login(csrf_client).status_code == 403  # login also needs CSRF
    assert csrf_client.post(
        "/api/admin/login/", {"email": "admin@example.com", "password": PASSWORD},
        format="json", **headers,
    ).status_code == 200
    headers = csrf_header(csrf_client)  # Django rotates the CSRF token at login

    url = f"/api/admin/profiles/{profile.id}/deactivate/"
    assert csrf_client.post(url).status_code == 403
    profile.refresh_from_db()
    assert profile.status == "active"

    assert csrf_client.post(url, **headers).status_code == 200
    profile.refresh_from_db()
    assert profile.status == "deactivated"


@pytest.mark.django_db
def test_user_cannot_deactivate_a_profile(client, user, profile):
    user_login(client)
    assert client.post(f"/api/admin/profiles/{profile.id}/deactivate/").status_code == 403
    profile.refresh_from_db()
    assert profile.status == "active"


@pytest.mark.django_db
def test_admin_logout_destroys_session_on_server(client, admin):
    admin_login(client)
    old_key = client.cookies["sessionid"].value
    assert Session.objects.filter(session_key=old_key).exists()
    assert client.get("/api/admin/me/").status_code == 200

    assert client.post("/api/admin/logout/").status_code == 204
    assert not Session.objects.filter(session_key=old_key).exists()

    client.cookies["sessionid"] = old_key  # replay the old cookie
    assert client.get("/api/admin/me/").status_code == 403


@pytest.mark.django_db
def test_deactivated_admin_session_stops_working(client, admin):
    admin_login(client)
    admin.is_active = False
    admin.save()
    assert client.get("/api/admin/me/").status_code == 403


@pytest.mark.django_db
def test_admin_cannot_be_demoted_session_keeps_role_from_database(client, admin):
    admin_login(client)
    admin.role = "user"
    admin.save()
    assert client.get("/api/admin/profiles/").status_code == 403


@pytest.mark.django_db
def test_deactivated_profile_listed_as_deactivated(client, admin, user):
    p = make_profile(user)
    admin_login(client)
    client.post(f"/api/admin/profiles/{p.id}/deactivate/")
    assert HealthProfile.objects.get(pk=p.pk).status == "deactivated"
    assert client.get("/api/admin/profiles/?status=deactivated").data["count"] == 1
