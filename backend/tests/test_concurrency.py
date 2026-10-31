"""
PostgreSQL concurrency: a member write racing an admin deactivation.

Policy under test: every change to a profile (member write or admin deactivate / reactivate) first
locks the profile row with SELECT ... FOR UPDATE and decides using that locked, fresh row. So no
member write can commit after a deactivation has committed, and admins decide "changed" correctly.

How the tests stay reliable (no sleep-and-hope timing):
  - The member and the admin run in two threads, each with its own real database connection.
  - A Pause stops one thread at an exact line until the test says "go" (threading.Event).
  - "Is that thread really waiting for the row lock?" is asked of PostgreSQL (pg_stat_activity).
  - Every wait has a deadline and fails with a clear message instead of hanging.
  - Cleanup always runs: pauses are released, threads joined, their connections closed, and any
    backend that is somehow still connected is terminated. An autouse fixture then checks that no
    other connection or lock is left on the test database, even after a failing test.
"""
import threading
import time

import pytest
from django.db import connection, connections

from adminpanel import views as admin_views
from audit.models import AuditEvent
from profiles import services
from profiles import views as member_views
from profiles.models import Demographics, EmergencyContact, HealthProfile

from .conftest import admin_login, make_profile, user_login

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(connection.vendor != "postgresql", reason="needs PostgreSQL row locks"),
]

WAIT = 10  # seconds: the longest any step may take before the test fails
ROOT = "/api/profiles/me/"
DENIED_MESSAGE = "Your profile is deactivated and can no longer be changed."

OTHER_CLIENT_BACKENDS = """
    SELECT count(*) FROM pg_stat_activity
    WHERE datname = current_database() AND backend_type = 'client backend' AND pid <> pg_backend_pid()
"""
WAITING_FOR_A_LOCK = OTHER_CLIENT_BACKENDS + " AND wait_event_type = 'Lock'"


# ------------------------------------------------------------------ helpers
class Worker(threading.Thread):
    """Runs one request in its own thread (= its own database connection) and keeps the result."""

    def __init__(self, name, request):
        super().__init__(name=name, daemon=True)
        self.request, self.response, self.error = request, None, None

    def run(self):
        try:
            with connection.cursor() as cursor:
                # Safety net: even if the test logic is wrong, this connection never waits forever.
                cursor.execute("SET lock_timeout = '15s'")
            self.response = self.request()
        except BaseException as exc:  # noqa: BLE001 - reported by the test, never swallowed
            self.error = exc
        finally:
            connections.close_all()  # closes only THIS thread's connections


class Pause:
    """Wraps a function so that the named thread stops just before calling it, until go() is called."""

    def __init__(self, thread_name):
        self.thread_name = thread_name
        self.reached, self._go = threading.Event(), threading.Event()

    def wrap(self, fn):
        def paused(*args, **kwargs):
            if threading.current_thread().name == self.thread_name and not self.reached.is_set():
                self.reached.set()
                if not self._go.wait(WAIT):
                    raise TimeoutError(f"{self.thread_name} was never released")
            return fn(*args, **kwargs)
        return paused

    def wait_until_reached(self):
        if not self.reached.wait(WAIT):
            pytest.fail(f"{self.thread_name} never reached its pause point")

    def go(self):
        self._go.set()


def _count(sql):
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchone()[0]


def wait_until_a_connection_is_blocked_on_a_lock():
    """Poll PostgreSQL itself until another connection is waiting for a row lock."""
    deadline = time.monotonic() + WAIT
    while time.monotonic() < deadline:
        if _count(WAITING_FOR_A_LOCK):
            return
        time.sleep(0.02)
    pytest.fail("no connection ever waited for the profile row lock")


@pytest.fixture(autouse=True)
def race():
    """
    Collects threads and pauses. After every test, pass or fail, in this order:
    release every pause, join every thread, terminate any session still connected (last resort),
    then check that no other connection and no lock is left on the test database.
    """
    state = {"workers": [], "pauses": []}

    def start(name, request):
        worker = Worker(name, request)
        state["workers"].append(worker)
        worker.start()
        return worker

    def pause(name):
        p = Pause(name)
        state["pauses"].append(p)
        return p

    yield start, pause

    for p in state["pauses"]:
        p.go()
    for worker in state["workers"]:
        worker.join(WAIT)
    if any(worker.is_alive() for worker in state["workers"]):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database()"
                           " AND backend_type = 'client backend' AND pid <> pg_backend_pid()")

    deadline = time.monotonic() + WAIT
    while _count(OTHER_CLIENT_BACKENDS) and time.monotonic() < deadline:
        time.sleep(0.02)  # a closed connection can take a moment to disappear from pg_stat_activity
    assert _count(OTHER_CLIENT_BACKENDS) == 0, "a thread left a database connection open"
    # Client connections only: PostgreSQL's own autovacuum may briefly lock system tables such as
    # pg_trigger on a freshly created test database, and that is not something a test left behind.
    assert _count("SELECT count(*) FROM pg_locks l JOIN pg_database d ON d.oid = l.database"
                  " JOIN pg_stat_activity a ON a.pid = l.pid AND a.backend_type = 'client backend'"
                  " WHERE d.datname = current_database() AND l.pid <> pg_backend_pid()") == 0, "a lock was left behind"


def finish(*workers):
    for worker in workers:
        worker.join(WAIT)
        assert not worker.is_alive(), f"{worker.name} did not finish"
        assert worker.error is None, f"{worker.name} raised {worker.error!r}"
    return [worker.response for worker in workers]


def profile_events(profile_id):
    return list(AuditEvent.objects.filter(target_type="health_profile", target_id=profile_id)
                .order_by("id").values_list("action", "outcome", "changed_fields"))


def logged_in_member(client):
    user_login(client)
    return client


def logged_in_admin(client_class):
    client = client_class()
    admin_login(client)
    return client


def assert_denied(response):
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
    assert response.json()["error"]["message"] == DENIED_MESSAGE


@pytest.fixture
def setup(client, user, admin):
    profile = make_profile(user, sections=("demographics", "contact"))  # city = Lahore, one contact
    return profile, logged_in_member(client), logged_in_admin(type(client))


# ------------------------------------------------------------------ A: deactivated before the member takes the lock
WRITES = {
    "patch demographics": ("patch", ROOT + "demographics/", {"city": "Karachi"}, "demographics.updated"),
    "create contact": ("post", ROOT + "emergency-contacts/",
                       {"name": "Bilal Ahmed", "relationship": "sibling", "phone": "+92 311 1112223"},
                       "emergency_contact.created"),
    "delete profile": ("delete", ROOT, None, "profile.deleted"),
}


@pytest.mark.parametrize("write", WRITES)
def test_a_member_passed_the_early_check_then_admin_deactivated(setup, race, monkeypatch, write):
    """The member passes the early check and stops just before taking the lock. The admin deactivates
    and commits. The member continues: it must see the fresh status under the lock and be refused."""
    profile, member, admin = setup
    method, url, body, action = WRITES[write]
    start, pause = race
    before_lock = pause("member")
    monkeypatch.setattr(services, "_lock", before_lock.wrap(services._lock))

    m = start("member", lambda: getattr(member, method)(url, body, format="json"))
    before_lock.wait_until_reached()
    assert admin.post(f"/api/admin/profiles/{profile.id}/deactivate/").status_code == 200  # committed
    before_lock.go()
    [response] = finish(m)

    assert_denied(response)
    assert HealthProfile.objects.filter(pk=profile.pk, status="deactivated").exists()  # not deleted
    assert Demographics.objects.get(profile=profile).city == "Lahore"
    assert EmergencyContact.objects.filter(profile=profile).count() == 1
    assert profile_events(profile.id) == [
        ("admin.profile_deactivated", "success", ["status"]),
        (action, "denied", []),  # committed, even though the member's transaction rolled back
    ]


# ------------------------------------------------------------------ B: the member waits on the admin's lock
def test_b_member_waits_for_the_admins_lock_then_sees_the_deactivation(setup, race, monkeypatch):
    """The admin holds the lock (status changed, not committed yet). The member arrives, passes the
    early check (it still reads 'active') and blocks on the lock. The admin commits. The member wakes
    up, re-reads the row under the lock, sees 'deactivated' and is refused."""
    profile, member, admin = setup
    start, pause = race
    admin_holds_lock = pause("admin")
    monkeypatch.setattr(admin_views, "record_event", admin_holds_lock.wrap(admin_views.record_event))

    a = start("admin", lambda: admin.post(f"/api/admin/profiles/{profile.id}/deactivate/"))
    admin_holds_lock.wait_until_reached()
    m = start("member", lambda: member.patch(ROOT + "demographics/", {"city": "Karachi"}, format="json"))
    wait_until_a_connection_is_blocked_on_a_lock()
    admin_holds_lock.go()
    admin_response, member_response = finish(a, m)

    assert admin_response.status_code == 200
    assert_denied(member_response)
    assert Demographics.objects.get(profile=profile).city == "Lahore"
    assert profile_events(profile.id) == [
        ("admin.profile_deactivated", "success", ["status"]),
        ("demographics.updated", "denied", []),
    ]


# ------------------------------------------------------------------ C: the admin waits on the member's lock
def test_c_admin_waits_for_the_members_lock_and_the_member_write_counts(setup, race, monkeypatch):
    """The member holds the lock (change made, not committed). The admin must wait for it. The member
    commits first, so its write is legitimate (200); then the admin deactivates."""
    profile, member, admin = setup
    start, pause = race
    member_holds_lock = pause("member")
    monkeypatch.setattr(member_views, "record_event", member_holds_lock.wrap(member_views.record_event))

    m = start("member", lambda: member.patch(ROOT + "demographics/", {"city": "Karachi"}, format="json"))
    member_holds_lock.wait_until_reached()
    a = start("admin", lambda: admin.post(f"/api/admin/profiles/{profile.id}/deactivate/"))
    wait_until_a_connection_is_blocked_on_a_lock()
    member_holds_lock.go()
    member_response, admin_response = finish(m, a)

    assert member_response.status_code == 200
    assert admin_response.status_code == 200
    assert Demographics.objects.get(profile=profile).city == "Karachi"
    assert HealthProfile.objects.get(pk=profile.pk).status == "deactivated"
    assert profile_events(profile.id) == [
        ("demographics.updated", "success", ["city"]),
        ("admin.profile_deactivated", "success", ["status"]),
    ]


# ------------------------------------------------------------------ D: two admins deactivate at once
def test_d_two_admin_deactivations_record_exactly_one_status_change(setup, race, monkeypatch, client):
    """Admin 1 holds the lock mid-deactivation. Admin 2 must wait, then decide from the fresh row:
    the profile is already deactivated, so it records no change (changed_fields == [])."""
    profile, _, admin1 = setup
    admin2 = logged_in_admin(type(client))
    start, pause = race
    first_holds_lock = pause("admin1")
    monkeypatch.setattr(admin_views, "record_event", first_holds_lock.wrap(admin_views.record_event))

    a1 = start("admin1", lambda: admin1.post(f"/api/admin/profiles/{profile.id}/deactivate/"))
    first_holds_lock.wait_until_reached()
    a2 = start("admin2", lambda: admin2.post(f"/api/admin/profiles/{profile.id}/deactivate/"))
    wait_until_a_connection_is_blocked_on_a_lock()
    first_holds_lock.go()
    responses = finish(a1, a2)

    assert [r.status_code for r in responses] == [200, 200]
    assert profile_events(profile.id) == [
        ("admin.profile_deactivated", "success", ["status"]),
        ("admin.profile_deactivated", "success", []),  # the second one changed nothing
    ]
