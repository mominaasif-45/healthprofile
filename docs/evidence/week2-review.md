# Week 2 review: evidence

Real output from the review-response work on `feature/week2-profiles-audit` (PR #3), captured on 2026-10-31.
Synthetic data only. Database output shows constraint names and PostgreSQL error codes, never phone values.

Commits: `6a5633f` audit durability · `15f7b1b` phone normalisation · `b8dd91a` lock and re-check ·
`3c58e99` primary contact · `40cb5ab` frontend phone check · the docs commit that adds this file.

## 1. Database: migrations from a clean database, catalog check, raw SQL attempts

A throwaway database (`healthprofile_phase5_fresh`) was created, migrated from zero, checked and dropped.
The same script against the local development database (already at `profiles/0008`) gave identical results.

```text
$ python manage.py migrate   (against healthprofile_phase5_fresh, a brand-new empty database)
  ...
  Applying profiles.0001_initial... OK
  Applying profiles.0002_week2_sections... OK
  Applying profiles.0003_copy_week1_data... OK
  Applying profiles.0004_remove_old_profile_columns... OK
  Applying profiles.0005_drop_redundant_fk_indexes... OK
  Applying profiles.0006_restore_one_primary_contact_constraint... OK
  Applying profiles.0007_normalize_contact_phones... OK
  Applying profiles.0008_contact_phone_is_canonical... OK
  ...   (38 migrations in total, all OK)

1) CATALOG: indexes on profiles_emergencycontact (pg_indexes)
   contact_one_primary_per_profile    UNIQUE btree (profile_id) WHERE is_primary
   contact_unique_phone_per_profile   UNIQUE btree (profile_id, phone)
   profiles_emergencycontact_pkey     UNIQUE btree (id)
   CATALOG: constraints (pg_constraint; c = check, u = unique, p = primary key)
   contact_phone_is_canonical         c  CHECK (((phone)::text ~ '^\+?[0-9]{7,15}$'::text))
   contact_unique_phone_per_profile   u  UNIQUE (profile_id, phone)
   profiles_emergencycontact_pkey     p  PRIMARY KEY (id)

2) RAW SQL (bypassing Django) on a synthetic profile that already has one primary contact
   INSERT a second primary contact              -> REJECTED  sqlstate=23505 constraint=contact_one_primary_per_profile
   INSERT phone '+92 300 0000103' (spaces)      -> REJECTED  sqlstate=23514 constraint=contact_phone_is_canonical
   INSERT phone '1------'                       -> REJECTED  sqlstate=23514 constraint=contact_phone_is_canonical
   INSERT the same number again                 -> REJECTED  sqlstate=23505 constraint=contact_unique_phone_per_profile

3) HONEST LIMIT: 'at least one primary' is enforced by the service, not the database
   UPDATE: untick the only primary              -> ACCEPTED by the database (rows: 1)
   primaries left on that profile: 0 (the API refuses this with 400; raw SQL is not stopped)

4) HONEST LIMIT: the audit log is append-only in the APPLICATION only
   ORM: AuditEvent.objects.filter().update()    -> REFUSED by the ORM guard (AppendOnlyError)
   raw SQL: UPDATE audit_auditevent             -> ACCEPTED by the database (rows: 1)
   raw SQL: DELETE FROM audit_auditevent        -> ACCEPTED by the database (rows: 1)
   -> direct database access needs its own restrictions (e.g. a role without UPDATE/DELETE, or triggers)

5) everything above was rolled back: synthetic users left = 0

$ DROP DATABASE healthprofile_phase5_fresh
dropped; databases named healthprofile_phase5_fresh left: 0
```

`23505` = unique violation, `23514` = check violation.

### Migrations 0007 / 0008 changed no existing constraint

Catalog of `profiles_emergencycontact` before `0007` and after `0008`: the only difference is one added line.
`makemigrations --check` reported "No changes detected", and `sqlmigrate profiles 0008` is a single `ADD CONSTRAINT`.

```diff
+  contact_phone_is_canonical  c  CHECK (((phone)::text ~ '^\+?[0-9]{7,15}$'::text))
```

Stored data on the development database: 6 contacts, all 6 rewritten to canonical form by `0007`
(punctuation removed, digits unchanged), 0 out of range, 0 same-profile collisions.

## 2. Fail-then-pass proof for every new test

Each new test file was run against the previous commit's source (with only the new tests added), then against the fix.
Tests that pass on both sides cover behaviour that was already correct; they guard against the fix breaking it.

| Phase | Tests | Old code | New code | Why the old code failed |
|---|---|---|---|---|
| 1 Audit durability | `test_audit_durability.py` | 13 failed | 13 passed | With the audit insert broken, writes still returned 200 / 201 / 204 and the change was kept |
| 2 Phone normalisation | `test_phone_normalisation.py` | 16 failed, 9 passed | 25 passed | `1------` and 16 digits accepted, raw formats stored, reformatted duplicates accepted, no DB CHECK, no migration |
| 3 Lock and re-check | `test_concurrency.py` | 5 failed, 1 passed | 6 passed | Member wrote after a committed deactivation (200 / 201); old delete took no lock; two admins both recorded a status change |
| 4 Primary contact | `test_primary_contact.py` | 4 failed, 3 passed | 7 passed | Unsetting the current primary returned 200 and left zero primaries |
| 4 Primary contact | `contacts-card.test.tsx` | 2 failed, 2 passed | 4 passed | Checkbox not disabled for the primary; an `is_primary` server error was not shown |
| 5 Frontend phone rule | `validation.test.ts` | 6 failed, 4 passed | 10 passed | 2 behaviour failures (`1------` and 16 digits accepted); 4 only because the message now matches the server's |

Phase 3 scenario C (admin waits for the member's lock) passes on the old code too: the old admin `UPDATE` also had to
wait for the member's row lock. Scenario D (two admins at once) is the test that fails on the old admin path.

## 3. Concurrency tests: 20 consecutive runs and cleanup

`tests/test_concurrency.py` run 20 times in a row, each in a fresh pytest process with a fresh test database:

```text
run  1..20: 6 passed (every run)     clean runs: 20 / 20     (7-18 s per run, mostly test-database creation)
```

The first two batches of 20 runs had 1 and 2 teardown errors. They were caused by the test's own leftover-lock check,
not by the application: a diagnostic showed the locks were on PostgreSQL's system table `pg_trigger`, taken by
autovacuum on the freshly created test database, not by any client connection. The check was narrowed to locks held
by client connections (which is what a leftover test thread would be), and the 20 / 20 batch above followed.

Cleanup under failure, shown with two deliberately failing tests (temporary file, deleted afterwards): one failed while
the member held the row lock and the admin waited on it; one had a thread stuck in a 60 s query, so the join timed out
and the fixture terminated that session. Both reported only their deliberate failure, no cleanup error. Afterwards the
server had 0 other client sessions, 0 locks held by client sessions and 0 leftover test databases.

## 4. Overlap with Week 1 PR #2 (not merged)

PR #2 (`fix/week1-review`, `69c7cc0`) and PR #3 both branch from `main` at `c07f684`. A throwaway merge on a temporary
local branch (deleted afterwards, never pushed) gave 10 conflicts. In each, PR #3 already contains its own later version
of the same Week 1 fix, so each was resolved by keeping PR #3's file:

| File | Why it conflicts | PR #3 already has |
|---|---|---|
| `backend/accounts/views.py` | both add CSRF to member login | `enforce_csrf` on member login |
| `backend/tests/test_jwt.py` | both add a "login without CSRF" test | `test_member_login_without_csrf_token_is_rejected_and_sets_no_cookies` |
| `backend/profiles/serializers.py`, `backend/tests/test_profiles.py` | PR #2 edits / tests the Week 1 one-row `completeness` | Week 2 section completion; "DOB or age range" as DB constraint + serializer check (`test_demographics_needs_dob_or_age_range`) |
| `frontend/components/ConfirmDialog.tsx` and its test | both add the component | later version; busy + Escape, focus on Cancel and fallback focus are all tested |
| `frontend/tests/admin-page.test.tsx`, `frontend/app/admin/page.tsx`, `frontend/app/admin/profiles/[id]/page.tsx` | Week 1 vs Week 2 admin UI | focus after deactivating **and** reactivating the last profile |
| `README.md` | Week 1 vs Week 2 test counts | Week 2 README (login row already says CSRF) |

Auto-merged without conflict and checked: `package.json` / `package-lock.json` / Vitest config are identical in both;
PR #2's line in `docs/ai-workflow.md` lands in the Week 1 "Verification" section; PR #2's 3 updated Week 1
screenshots are only used in the README's Week 1 gallery. After resolution, the merge changes no code compared with
PR #3, only those Week 1 docs and screenshots.

Checks on the temporary merge commit (`317cdfa`, parents `40cb5ab` + `69c7cc0`; deleted afterwards):

```text
makemigrations --check: No changes detected
pytest: 275 passed
npm test: Tests  24 passed (24)
npm run lint exit: 0 · tsc exit: 0 · npm run build exit: 0
```

## 5. Final validation

The final migrations, backend tests, frontend tests, lint, type-check and build were run on the commit that adds this
file. That commit cannot contain its own hash, so the tested commit is named in the PR #3 conversation.
