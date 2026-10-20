"""
Prints the SQL and the real PostgreSQL plan (EXPLAIN ANALYZE, BUFFERS) for the three lookups
that our composite indexes were built for. Nothing here is faked: if Postgres picks another
plan, that plan is what you see.

  python manage.py seed_profiles --bulk 1000
  python manage.py explain_queries
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count

from accounts.models import User
from audit.models import AuditEvent
from profiles.models import HealthProfile


class Command(BaseCommand):
    help = "Print EXPLAIN (ANALYZE, BUFFERS) for the admin list, member activity and profile history queries."

    def add_arguments(self, parser):
        parser.add_argument("--status", default="deactivated", choices=["active", "deactivated"],
                            help="Status for query 1 (default deactivated: a selective value).")
        parser.add_argument("--no-analyze", action="store_true",
                            help="Skip ANALYZE (refreshing table statistics) before explaining.")

    def handle(self, *args, **options):
        if not AuditEvent.objects.exists():
            raise CommandError("No audit events yet. Run: python manage.py seed_profiles --bulk 1000")

        if not options["no_analyze"]:
            # Freshly bulk-loaded tables have no statistics yet; autovacuum would do this soon anyway.
            with connection.cursor() as cursor:
                cursor.execute("ANALYZE profiles_healthprofile")
                cursor.execute("ANALYZE audit_auditevent")
            self.stdout.write("(ran ANALYZE on profiles_healthprofile and audit_auditevent first)\n")

        counts = (
            f"Rows: {HealthProfile.objects.count()} profiles "
            f"({HealthProfile.objects.filter(status=options['status']).count()} {options['status']}), "
            f"{AuditEvent.objects.count()} audit events"
        )
        self.stdout.write(counts + "\n")

        # Pick the member with the most events, a typical "active" user for the activity page.
        actor_id = (
            AuditEvent.objects.filter(actor__role=User.Role.USER)
            .order_by().values("actor").annotate(n=Count("id")).order_by("-n")
            .values_list("actor", flat=True).first()
        )
        profile_id = (
            AuditEvent.objects.filter(target_type="health_profile", target_id__isnull=False)
            .order_by("-created_at").values_list("target_id", flat=True).first()
        )

        queries = [
            (
                "1) Admin list filtered by status, newest first  (index: profile_status_created_idx)",
                HealthProfile.objects.filter(status=options["status"]).order_by("-created_at"),
            ),
            (
                f"2) Member activity page for user id {actor_id}, newest first  (index: audit_actor_created_idx)",
                AuditEvent.objects.filter(actor_id=actor_id).order_by("-created_at", "-id")[:10],
            ),
            (
                f"3) History of profile id {profile_id}, newest first  (index: audit_target_created_idx)",
                AuditEvent.objects.filter(target_type="health_profile", target_id=profile_id).order_by(
                    "-created_at", "-id"
                )[:10],
            ),
        ]
        for title, queryset in queries:
            self.stdout.write(self.style.MIGRATE_HEADING("\n" + title))
            self.stdout.write("SQL:\n  " + str(queryset.query))
            self.stdout.write("PLAN:\n" + queryset.explain(analyze=True, buffers=True))
