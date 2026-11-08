"""
EVIDENCE TOOLING ONLY. Not part of the app: nothing imports it and the test suite does not run it.

Run from the repository root, with the backend venv active and PostgreSQL running:
    python docs/evidence/capture_enforcement.py
It writes to the database configured for the backend (it creates and then deletes two throwaway accounts;
the admin's append-only sign-in / sign-out audit rows remain, with the actor set to empty).

Captures server-enforcement evidence for POST /api/ml/v1/no-show/predict/ over REAL HTTP:
  1. starts the backend (manage.py runserver) on a free local port,
  2. creates a throwaway member and a throwaway admin (admin via `manage.py create_admin`, in-process)
     with random passwords that stay in memory only: never printed, logged or saved,
  3. sends six requests with a CSRF-aware client (gets /api/csrf/, sends X-CSRFToken unless told not to)
     and prints label, expected status, real status and JSON body,
  4. signs both out, deletes both accounts and stops the server (always, even on failure).

backend/.env is never opened by this script; the server and Django read their own settings as usual.
The client sends cookies marked Secure over plain http://127.0.0.1 (a browser treats localhost the same way).
"""
import http.cookiejar
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"  # docs/evidence/ -> repository root -> backend/
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()
from django.core.management import call_command  # noqa: E402

from accounts.models import User  # noqa: E402
from audit.models import AuditEvent  # noqa: E402

ENDPOINT = "/api/ml/v1/no-show/predict/"
# The Swagger request example "Fictional appointment (likely no-show)" from ml/views.py.
EXAMPLE = {"lead_time_days": 21, "weekday": "mon", "hour": 9, "visit_type": "new_visit", "booking_channel": "online",
           "reminder_sent": "no", "prior_visits": 3, "prior_no_shows": 1, "distance_band": "15_30km",
           "age_band": None}


class LocalhostSecureCookies(http.cookiejar.DefaultCookiePolicy):
    def return_ok_secure(self, cookie, request):
        return True


class Client:
    def __init__(self, base):
        self.base = base
        self.jar = http.cookiejar.CookieJar(policy=LocalhostSecureCookies())
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def cookie(self, name):
        return next((c.value for c in self.jar if c.name == name), None)

    def fetch_csrf(self):
        status, _ = self.send("GET", "/api/csrf/", send_csrf=False)
        assert status == 200 and self.cookie("csrftoken"), "could not get a CSRF cookie"

    def send(self, method, path, body=None, send_csrf=True):
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if send_csrf:
            headers["X-CSRFToken"] = self.cookie("csrftoken") or ""
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=20) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"null")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until_up(base):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/health/", timeout=2) as r:
                if r.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("the server did not start within 60 s")


def main():
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    tag = secrets.token_hex(4)
    member_email, admin_email = f"evidence-member-{tag}@example.test", f"evidence-admin-{tag}@example.test"
    started = None
    server = subprocess.Popen([sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
                              cwd=BACKEND, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    member, admin = Client(base), Client(base)
    try:
        wait_until_up(base)
        print(f"server: manage.py runserver on {base} (pid {server.pid})")

        from django.utils import timezone
        started = timezone.now()
        User.objects.create_user(email=member_email, password=(member_pw := secrets.token_urlsafe(24)),
                                 name="Evidence Member")
        call_command("create_admin", email=admin_email, name="Evidence Admin",
                     password=(admin_pw := secrets.token_urlsafe(24)), stdout=open(os.devnull, "w"))
        print(f"throwaway accounts created: {member_email} (member), {admin_email} (admin); passwords not shown")

        member.fetch_csrf()
        status, _ = member.send("POST", "/api/auth/user/login/", {"email": member_email, "password": member_pw})
        assert status == 200, f"member sign-in failed: {status}"
        admin.fetch_csrf()
        status, _ = admin.send("POST", "/api/admin/login/", {"email": admin_email, "password": admin_pw})
        assert status == 200, f"admin sign-in failed: {status}"
        admin.fetch_csrf()  # Django rotates the CSRF token when an admin session starts
        del member_pw, admin_pw
        signed_out = Client(base)
        signed_out.fetch_csrf()

        cases = [
            ("1 valid Swagger example, member", 200, member, EXAMPLE, True),
            ("2 lead_time_days 91, member", 400, member, {**EXAMPLE, "lead_time_days": 91}, True),
            ("3 extra field role: 'admin', member", 400, member, {**EXAMPLE, "role": "admin"}, True),
            ("4 member, no X-CSRFToken header", 403, member, EXAMPLE, False),
            ("5 signed out (CSRF cookie + header, no sign-in)", 401, signed_out, EXAMPLE, True),
            ("6 admin session (sessionid + X-CSRFToken)", 401, admin, EXAMPLE, True),
        ]
        differs = []
        for label, expected, client, body, send_csrf in cases:
            status, payload = client.send("POST", ENDPOINT, body, send_csrf=send_csrf)
            verdict = "as expected" if status == expected else "DIFFERS FROM EXPECTED"
            if status != expected:
                differs.append(label)
            print(f"\n=== ({label}) expected {expected}, got HTTP {status}: {verdict}")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("\nall six statuses as expected" if not differs else f"\nDIFFERENT: {differs}")
    finally:
        if member.cookie("csrftoken"):
            member.send("POST", "/api/auth/user/logout/", {})
        if admin.cookie("sessionid"):
            admin.send("POST", "/api/admin/logout/", {})
        deleted, _ = User.objects.filter(email__in=[member_email, admin_email]).delete()
        server.terminate()
        server.wait(timeout=20)
        left = User.objects.filter(email__in=[member_email, admin_email]).count()
        print(f"\ncleanup: delete() removed {deleted} rows (the accounts and anything that cascades from them); "
              f"throwaway accounts left: {left}; server pid {server.pid} exit code {server.returncode}")
        if started:
            rows = list(AuditEvent.objects.filter(created_at__gte=started).order_by("id")
                        .values_list("action", "outcome", "actor_role", "actor_id"))
            print(f"audit rows written during the run (append-only, kept by design): {rows}")
        print(f"PORT={port}")


if __name__ == "__main__":
    main()
