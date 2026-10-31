# CLAUDE.md — rules for AI assistants in this repo

## Project
HealthProfile: role-based wellness profile builder. Django + DRF + PostgreSQL in backend/, Next.js + TypeScript in frontend/. Synthetic data only. Not a medical tool.

## Commands
- Backend (from backend/, venv active): `python manage.py runserver`, `python -m pytest`, `python manage.py makemigrations --check`, `python manage.py migrate`
- Frontend (from frontend/): `npm run dev`, `npm run lint`, `npm run build`

## Security rules (never break)
- Members: JWT in HttpOnly cookies only. Never return tokens in a body or use localStorage.
- Admins: created only by `manage.py create_admin`; session auth + CSRF. No public admin signup.
- Every view declares authentication_classes and permission_classes. Default authentication is empty on purpose.
- Members reach data only through /api/profiles/me/...; never add a member route with another profile's ID.
- Never accept `role`, `status`, `is_staff` or `is_superuser` from a request body.
- Never log or audit values, passwords, tokens, cookies, session keys, phone numbers, allergies or search terms. Audit events store field names only.
- Secrets come from .env only. Never read, print or commit backend/.env.
- No real patient data, no diagnosis, no clinical advice.

## How to work
- Inspect -> plan -> STOP for "go" -> tests first -> implement -> validate.
- Only touch files in the current phase's scope; if something else must change, stop and ask.
- New migrations only; never edit applied migrations.
- No new dependencies without approval.
- Do not commit, push, rebase or reset. Show `git diff --stat` at the end.
- Keep the error shape {"error": {"code", "message", "fields"}}.
- Explain changes in beginner-friendly language.
