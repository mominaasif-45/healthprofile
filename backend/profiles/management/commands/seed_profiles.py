import random
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.utils import timezone
from faker import Faker

from accounts.models import User
from profiles.models import HealthProfile

DEMO_PASSWORD = "CalmMorning2026"

GOALS = [
    "Sleep 7+ hours",
    "Walk 8,000 steps",
    "Reduce stress",
    "More vegetables",
    "Drink more water",
    "Stretch daily",
    "Cut back on sugar",
    "Meditate 10 minutes",
]

# name, email, age range, contact, goals, allergies, emergency contact, status, days ago
DEMO = [
    ("Momina Asif", "momina.asif@example.com", "25-34", "email",
     ["Sleep 7+ hours", "Walk 8,000 steps"], "Peanuts", "Bilal Ahmed", "active", 2),
    ("Bilal Ahmed", "bilal.ahmed@example.com", "35-44", "phone",
     ["Reduce stress"], "", "Sana Ahmed", "active", 3),
    ("Sara Noor", "sara.noor@example.com", "18-24", "sms",
     ["More vegetables", "Walk 8,000 steps"], "Shellfish", "Noor Hussain", "active", 4),
    ("Hamza Malik", "hamza.malik@example.com", "45-54", "email",
     ["Sleep 7+ hours"], "", "Iqra Malik", "deactivated", 5),
    ("Zainab Iqbal", "zainab.iqbal@example.com", "25-34", "phone",
     ["Reduce stress", "More vegetables"], "Dust", "Omar Iqbal", "active", 7),
]


class Command(BaseCommand):
    help = "Create 5 synthetic demo members. Use --bulk N to add N more for the EXPLAIN demo."

    def add_arguments(self, parser):
        parser.add_argument("--bulk", type=int, default=0, help="Extra random members to add.")

    def handle(self, *args, **options):
        now = timezone.now()

        for name, email, age, contact, goals, allergies, emergency, status, days in DEMO:
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email=email, password=DEMO_PASSWORD, name=name)
            profile, _ = HealthProfile.objects.update_or_create(
                user=user,
                defaults=dict(
                    full_name=name,
                    age_range=age,
                    contact_preference=contact,
                    wellness_goals=goals,
                    allergies=allergies,
                    emergency_contact_name=emergency,
                    emergency_contact_phone="+92 300 0000000",
                    lifestyle_notes=(
                        "Desk job, try to walk after lunch. Prefer morning reminders."
                        if email.startswith("momina") else ""
                    ),
                    status=status,
                ),
            )
            # auto_now_add can't be set on create, so backdate with update()
            HealthProfile.objects.filter(pk=profile.pk).update(
                created_at=now - timedelta(days=days)
            )
        self.stdout.write(self.style.SUCCESS(
            f"5 demo members ready. Password for all: {DEMO_PASSWORD}"
        ))

        bulk = options["bulk"]
        if bulk > 0:
            self._bulk(bulk, now)

    def _bulk(self, count, now):
        fake = Faker()
        Faker.seed(2026)
        rng = random.Random(2026)
        password_hash = make_password(DEMO_PASSWORD)  # hash once: hashing 1,000 times is slow

        start = User.objects.filter(email__endswith="@seed.example.com").count()
        users = [
            User(
                email=f"member{start + i + 1}@seed.example.com",
                name=fake.name(),
                password=password_hash,
                role=User.Role.USER,
            )
            for i in range(count)
        ]
        User.objects.bulk_create(users)
        users = list(User.objects.filter(
            email__in=[u.email for u in users]
        ).order_by("id"))

        profiles = [
            HealthProfile(
                user=u,
                full_name=u.name,
                age_range=rng.choice(HealthProfile.AgeRange.values),
                contact_preference=rng.choice(HealthProfile.ContactPreference.values),
                wellness_goals=rng.sample(GOALS, k=rng.randint(1, 3)),
                emergency_contact_name=fake.name(),
                emergency_contact_phone="+92 300 0000000",
                status=rng.choices(["active", "deactivated"], weights=[9, 1])[0],
            )
            for u in users
        ]
        created = HealthProfile.objects.bulk_create(profiles)
        # spread created_at over the past year so ORDER BY created_at DESC is meaningful
        for p in created:
            HealthProfile.objects.filter(pk=p.pk).update(
                created_at=now - timedelta(minutes=rng.randint(1, 60 * 24 * 365))
            )
        self.stdout.write(self.style.SUCCESS(f"{count} bulk synthetic members added."))
