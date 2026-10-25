import pytest
from freezegun import freeze_time

from .conftest import PASSWORD, csrf_header, user_login


@pytest.mark.django_db
def test_login_sets_httponly_cookies_and_no_token_in_body(client, user):
    res = user_login(client)
    assert res.status_code == 200
    assert res.data["email"] == "momina@example.com"
    assert "access" not in res.data and "refresh" not in res.data
    assert res.cookies["access"]["httponly"]
    assert res.cookies["refresh"]["httponly"]
    assert res.cookies["access"]["samesite"] == "Lax"
    assert res.cookies["refresh"]["path"] == "/api/auth/user/"


@pytest.mark.django_db
def test_wrong_password_returns_401(client, user):
    assert user_login(client, password="WrongPassword123").status_code == 401


@pytest.mark.django_db
def test_unknown_email_returns_401(client, user):
    assert user_login(client, email="nobody@example.com").status_code == 401


@pytest.mark.django_db
def test_inactive_user_cannot_log_in(client, user):
    user.is_active = False
    user.save()
    assert user_login(client).status_code == 401


@pytest.mark.django_db
def test_login_is_throttled_after_five_attempts(client, user):
    codes = [user_login(client, password="Wrong-password-1").status_code for _ in range(6)]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429


@pytest.mark.django_db
def test_admin_cannot_use_user_login(client, admin):
    res = user_login(client, email="admin@example.com")
    assert res.status_code == 403


@pytest.mark.django_db
def test_me_works_with_valid_cookie(client, user):
    user_login(client)
    res = client.get("/api/auth/me/")
    assert res.status_code == 200
    assert res.data["name"] == "Momina Asif"


@pytest.mark.django_db
def test_expired_access_token_returns_401(client, user):
    with freeze_time("2026-10-19 10:00:00"):
        user_login(client)
        assert client.get("/api/auth/me/").status_code == 200
    with freeze_time("2026-10-19 10:16:00"):  # access token lives 15 minutes
        assert client.get("/api/auth/me/").status_code == 401


@pytest.mark.django_db
def test_tampered_or_garbage_token_returns_401(client, user):
    client.cookies["access"] = "not.a.jwt"
    assert client.get("/api/auth/me/").status_code == 401

    user_login(client)
    real = client.cookies["access"].value
    client.cookies["access"] = real[:-3] + ("aaa" if not real.endswith("aaa") else "bbb")
    assert client.get("/api/auth/me/").status_code == 401


@pytest.mark.django_db
def test_refresh_rotates_and_old_refresh_is_blacklisted(client, user):
    user_login(client)
    old_refresh = client.cookies["refresh"].value
    res = client.post("/api/auth/user/refresh/")
    assert res.status_code == 200
    assert client.cookies["refresh"].value != old_refresh

    client.cookies["refresh"] = old_refresh  # replay the rotated-out token
    assert client.post("/api/auth/user/refresh/").status_code == 401


@pytest.mark.django_db
def test_refresh_after_logout_returns_401(client, user):
    user_login(client)
    old_refresh = client.cookies["refresh"].value
    assert client.post("/api/auth/user/logout/").status_code == 204

    client.cookies["refresh"] = old_refresh
    assert client.post("/api/auth/user/refresh/").status_code == 401


@pytest.mark.django_db
def test_user_post_without_csrf_token_is_rejected(csrf_client, user):
    headers = csrf_header(csrf_client)
    login = csrf_client.post(
        "/api/auth/user/login/", {"email": "momina@example.com", "password": PASSWORD},
        format="json", **headers,
    )
    assert login.status_code == 200
    body = {"full_name": "Momina Asif", "age_range": "25-34"}
    assert csrf_client.post("/api/profiles/me/", body, format="json").status_code == 403
    assert csrf_client.post("/api/profiles/me/", body, format="json", **headers).status_code == 201


@pytest.mark.django_db
def test_user_login_without_csrf_token_is_rejected(csrf_client, user):
    headers = csrf_header(csrf_client)
    body = {"email": "momina@example.com", "password": PASSWORD}
    res = csrf_client.post("/api/auth/user/login/", body, format="json")
    assert res.status_code == 403
    assert "access" not in res.cookies and "refresh" not in res.cookies
    assert csrf_client.post("/api/auth/user/login/", body, format="json", **headers).status_code == 200
