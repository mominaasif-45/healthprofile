"""
Synthetic data only: fictional names, fictional phone numbers, no real people.

  python manage.py seed_profiles            # 5 demo members with different completion levels
  python manage.py seed_profiles --bulk 1000   # + N random members (about 5 audit events each)

Re-running is safe: the 5 demo members are rebuilt from scratch each time.
"""
import random
import uuid
from contextlib import contextmanager
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker

from accounts.models import User
from audit.models import AuditEvent
from profiles.models import (
    Demographics,
    EmergencyContact,
    HealthProfile,
    WellnessGoal,
    WellnessPreference,
)
from profiles.services import SECTION_WEIGHT, status_for_percent

DEMO_PASSWORD = "CalmMorning2026"
CITIES = ["Lahore", "Karachi", "Islamabad", "Multan", "Peshawar", "Quetta", "Faisalabad"]
GOALS = [g for g, _ in WellnessGoal.Goal.choices]
SECTIONS = ("demographics", "contact", "wellness", "goals")

# name, email, sections filled, status, age_range, date_of_birth, contact (name, relationship, phone), days ago created
DEMO = [
    ("Momina Asif", "momina.asif@example.com", SECTIONS, "active", "25-34", None,
     ("Bilal Ahmed", "sibling", "+923000000001"), 2),
    ("Bilal Ahmed", "bilal.ahmed@example.com", ("demographics", "contact", "wellness"), "active", "35-44", None,
     ("Sana Ahmed", "partner", "+923000000002"), 3),
    ("Sara Noor", "sara.noor@example.com", ("demographics", "wellness", "goals"), "active", None, "2004-03-12",
     None, 4),
    ("Hamza Malik", "hamza.malik@example.com", SECTIONS, "deactivated", "45-54", None,
     ("Iqra Malik", "parent", "+923000000004"), 5),
    ("Zainab Iqbal", "zainab.iqbal@example.com", (), "active", None, None, None, 7),
]


@contextmanager
def keep_given_timestamps():
    """Seeding needs back-dated created_at values; auto_now_add would overwrite them with 'now'."""
    field = AuditEvent._meta.get_field("created_at")
    field.auto_now_add = False
    try:
        yield
    finally:
        field.auto_now_add = True


def percent_for(sections):
    return len(sections) * SECTION_WEIGHT


class Command(BaseCommand):
    help = "Create 5 synthetic demo members (+ audit history). --bulk N adds N more for EXPLAIN demos."

    def add_arguments(self, parser):
        parser.add_argument("--bulk", type=int, default=0, help="Extra random members to add.")

    def handle(self, *args, **options):
        now = timezone.now()
        with keep_given_timestamps(), transaction.atomic():
            self._demo(now)
            if options["bulk"] > 0:
                self._bulk(options["bulk"], now)

    # ------------------------------------------------------------------ the 5 demo members
    def _demo(self, now):
        events = []
        admin = User.objects.filter(role=User.Role.ADMIN).order_by("id").first()

        for name, email, sections, status, age_range, dob, contact, days in DEMO:
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email=email, password=DEMO_PASSWORD, name=name)
            else:
                user.name = name
                user.save(update_fields=["name"])
            # Rebuild from scratch. _raw_delete skips the append-only guard on purpose:
            # this is a developer seed command, not application code.
            old_ids = list(HealthProfile.objects.filter(user=user).values_list("id", flat=True))
            AuditEvent.objects.filter(actor=user)._raw_delete(AuditEvent.objects.db)
            AuditEvent.objects.filter(target_type="health_profile", target_id__in=old_ids)._raw_delete(
                AuditEvent.objects.db
            )
            HealthProfile.objects.filter(user=user).delete()

            created = now - timedelta(days=days)
            profile = HealthProfile.objects.create(user=user, status="active")
            actions = [("profile.created", [])]

            if "demographics" in sections:
                Demographics.objects.create(
                    profile=profile, full_name=name, preferred_name=name.split()[0], age_range=age_range,
                    date_of_birth=dob, gender="female" if name.split()[0] in ("Momina", "Sara", "Zainab") else "male",
                    city=random.Random(email).choice(CITIES),
                )
                actions.append(("demographics.updated", ["age_range", "city", "full_name", "gender", "preferred_name"]))
            if "contact" in sections and contact:
                EmergencyContact.objects.create(
                    profile=profile, name=contact[0], relationship=contact[1], phone=contact[2], is_primary=True
                )
                actions.append(("emergency_contact.created", ["name", "phone", "relationship"]))
            if "wellness" in sections:
                preference = WellnessPreference.objects.create(
                    profile=profile, contact_preference=["email", "phone", "sms"][len(name) % 3],
                    activity_level="moderate", diet_preference="no_preference", sleep_goal_hours=8,
                    allergies="Peanuts" if email.startswith("momina") else "",
                    lifestyle_notes="Desk job, try to walk after lunch. Prefer morning reminders."
                    if email.startswith("momina") else "",
                )
                actions.append(("wellness.updated", ["allergies", "contact_preference", "lifestyle_notes"]))
                if "goals" in sections:
                    for goal in ("better_sleep", "more_activity"):
                        WellnessGoal.objects.create(preference=preference, goal=goal)
                    actions.append(("goals.updated", ["goals"]))

            percent = percent_for([s for s in sections if s != "contact" or contact])
            if "goals" in sections and "wellness" not in sections:
                percent -= SECTION_WEIGHT
            HealthProfile.objects.filter(pk=profile.pk).update(
                created_at=created, status=status, completion_percent=percent,
                completion_status=status_for_percent(percent),
            )

            for step, (action, fields) in enumerate(actions):
                events.append(self._event(user, action, profile.id, fields, created + timedelta(minutes=5 * step)))

            if admin and email.startswith(("momina", "hamza")):
                events.append(self._event(admin, "admin.profile_viewed", profile.id, [], now - timedelta(hours=3)))
            if admin and status == "deactivated":
                events.append(self._event(admin, "admin.profile_deactivated", profile.id, ["status"], now - timedelta(hours=2)))

        if admin:
            events.append(self._event(admin, "admin.login", None, [], now - timedelta(hours=4)))
        AuditEvent.objects.bulk_create(events)
        self.stdout.write(self.style.SUCCESS(
            f"5 demo members ready (1 complete, 2 in progress, 1 not started, 1 deactivated). "
            f"Password for all: {DEMO_PASSWORD}"
        ))

    @staticmethod
    def _event(actor, action, profile_id, fields, when, outcome="success"):
        return AuditEvent(
            actor=actor, actor_role=actor.role, action=action,
            target_type="health_profile" if profile_id else "", target_id=profile_id,
            changed_fields=fields, request_id=uuid.uuid4(), outcome=outcome, created_at=when,
        )

    # ------------------------------------------------------------------ N random members
    def _bulk(self, count, now):
        fake = Faker()
        Faker.seed(2026)
        rng = random.Random(2026)
        password_hash = make_password(DEMO_PASSWORD)  # hash once: hashing 1,000 times is slow

        start = User.objects.filter(email__endswith="@seed.example.com").count()
        users = User.objects.bulk_create([
            User(email=f"member{start + i + 1}@seed.example.com", name=fake.name(), password=password_hash,
                 role=User.Role.USER)
            for i in range(count)
        ])

        plan = []  # (user, sections, created_at)
        for user in users:
            level = rng.choices([0, 1, 2, 3, 4], weights=[1, 2, 3, 3, 6])[0]
            plan.append((user, SECTIONS[:level], now - timedelta(minutes=rng.randint(60, 60 * 24 * 90))))

        profiles = HealthProfile.objects.bulk_create([
            HealthProfile(
                user=user, status=rng.choices(["active", "deactivated"], weights=[9, 1])[0],
                completion_percent=percent_for(sections), completion_status=status_for_percent(percent_for(sections)),
            )
            for user, sections, _ in plan
        ])
        # bulk_create ignores auto_now_add overrides, so spread created_at with one UPDATE per profile
        for profile, (_, _, created) in zip(profiles, plan):
            HealthProfile.objects.filter(pk=profile.pk).update(created_at=created)

        demographics, contacts, preferences = [], [], []
        for profile, (user, sections, _) in zip(profiles, plan):
            if "demographics" in sections:
                demographics.append(Demographics(
                    profile=profile, full_name=user.name, age_range=rng.choice(Demographics.AgeRange.values),
                    gender=rng.choice(Demographics.Gender.values), city=rng.choice(CITIES),
                ))
            if "contact" in sections:
                contacts.append(EmergencyContact(
                    profile=profile, name=fake.name(), relationship=rng.choice(EmergencyContact.Relationship.values),
                    phone=f"+92300{rng.randint(1000000, 9999999)}", is_primary=True,
                ))
            if "wellness" in sections:
                preferences.append(WellnessPreference(
                    profile=profile, contact_preference=rng.choice(WellnessPreference.ContactPreference.values),
                    activity_level=rng.choice(WellnessPreference.ActivityLevel.values), sleep_goal_hours=rng.randint(6, 9),
                ))
        Demographics.objects.bulk_create(demographics)
        EmergencyContact.objects.bulk_create(contacts)
        preferences = WellnessPreference.objects.bulk_create(preferences)
        by_profile = {p.profile_id: p for p in preferences}
        goals = []
        for profile, (_, sections, _) in zip(profiles, plan):
            if "goals" in sections and profile.pk in by_profile:
                goals += [WellnessGoal(preference=by_profile[profile.pk], goal=g) for g in rng.sample(GOALS, rng.randint(1, 3))]
        WellnessGoal.objects.bulk_create(goals)

        # about 5 audit events per profile, spread over the time after the profile was created
        events = []
        for profile, (user, sections, created) in zip(profiles, plan):
            steps = [("profile.created", [])]
            if "demographics" in sections:
                steps.append(("demographics.updated", ["age_range", "city", "full_name"]))
            if "contact" in sections:
                steps.append(("emergency_contact.created", ["name", "phone", "relationship"]))
            if "wellness" in sections:
                steps.append(("wellness.updated", ["contact_preference", "sleep_goal_hours"]))
            if "goals" in sections:
                steps.append(("goals.updated", ["goals"]))
            while len(steps) < 5:
                steps.append(("demographics.updated", [rng.choice(["city", "preferred_name", "gender"])]))
            for step, (action, fields) in enumerate(steps):
                when = created + timedelta(minutes=rng.randint(1, 600) * (step + 1))
                events.append(self._event(user, action, profile.pk, fields, min(when, now)))
        AuditEvent.objects.bulk_create(events, batch_size=2000)
        self.stdout.write(self.style.SUCCESS(f"{count} bulk members, {len(events)} audit events added."))
