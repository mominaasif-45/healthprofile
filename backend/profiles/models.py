from django.conf import settings
from django.db import models
from django.db.models import F, Q

from .phones import CANONICAL as CANONICAL_PHONE


class HealthProfile(models.Model):
    """
    The root row: one per user (OneToOne). All personal data lives in the
    related section tables below, so each table has one job and one set of
    constraints. Deleting the user or the profile cascades to every section.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DEACTIVATED = "deactivated", "Deactivated"

    class CompletionStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETE = "complete", "Complete"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="health_profile"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    # Stored (not computed on the fly) so admins can filter and sort by it cheaply.
    # recalculate_completion() in profiles/services.py is the only writer.
    completion_status = models.CharField(
        max_length=12, choices=CompletionStatus.choices, default=CompletionStatus.NOT_STARTED
    )
    completion_percent = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["active", "deactivated"]),
                name="profile_status_is_valid",
            ),
            models.CheckConstraint(
                condition=Q(completion_status__in=["not_started", "in_progress", "complete"]),
                name="profile_completion_status_is_valid",
            ),
            models.CheckConstraint(
                condition=Q(completion_percent__gte=0, completion_percent__lte=100),
                name="profile_completion_percent_0_100",
            ),
        ]
        indexes = [
            # Query: admin list filtered by status, newest first
            #   WHERE status = %s ORDER BY created_at DESC
            # completion_status is deliberately NOT indexed: it has only 3 values,
            # so an index would rarely beat a scan (see README, architecture decisions).
            models.Index(fields=["status", "-created_at"], name="profile_status_created_idx"),
        ]

    def __str__(self):
        return f"Profile of user {self.user_id} ({self.status})"


class Demographics(models.Model):
    """Fictional personal details. Section 1 of 4."""

    class AgeRange(models.TextChoices):
        R18_24 = "18-24", "18-24"
        R25_34 = "25-34", "25-34"
        R35_44 = "35-44", "35-44"
        R45_54 = "45-54", "45-54"
        R55_64 = "55-64", "55-64"
        R65_PLUS = "65+", "65+"

    class Gender(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        NON_BINARY = "non_binary", "Non-binary"
        PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"

    profile = models.OneToOneField(HealthProfile, on_delete=models.CASCADE, related_name="demographics")
    full_name = models.CharField(max_length=120)
    preferred_name = models.CharField(max_length=60, blank=True, default="")
    date_of_birth = models.DateField(null=True, blank=True)
    age_range = models.CharField(max_length=10, choices=AgeRange.choices, null=True, blank=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True, default="")
    city = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(date_of_birth__isnull=False) | Q(age_range__isnull=False),
                name="demographics_needs_dob_or_age_range",
            ),
        ]

    def __str__(self):
        return self.full_name


class EmergencyContact(models.Model):
    """Up to 3 per profile (enforced in the service layer). Phone numbers are fictional."""

    class Relationship(models.TextChoices):
        PARENT = "parent", "Parent"
        SIBLING = "sibling", "Sibling"
        PARTNER = "partner", "Partner"
        FRIEND = "friend", "Friend"
        OTHER = "other", "Other"

    # db_index=False: the unique constraint (profile, phone) below already starts with profile,
    # so "all contacts of this profile" is served by it and a second index would be redundant.
    profile = models.ForeignKey(
        HealthProfile, on_delete=models.CASCADE, related_name="emergency_contacts", db_index=False
    )
    name = models.CharField(max_length=120)
    relationship = models.CharField(max_length=10, choices=Relationship.choices)
    phone = models.CharField(max_length=25)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # The same number cannot be added twice to one profile. Phones are stored in canonical
            # form (constraint below), so this also catches the same number typed differently.
            models.UniqueConstraint(fields=["profile", "phone"], name="contact_unique_phone_per_profile"),
            # Canonical form only: optional "+" then 7 to 15 digits (see profiles/phones.py).
            models.CheckConstraint(condition=Q(phone__regex=CANONICAL_PHONE), name="contact_phone_is_canonical"),
            # At most one primary contact per profile (partial unique index).
            models.UniqueConstraint(
                fields=["profile"], condition=Q(is_primary=True), name="contact_one_primary_per_profile"
            ),
        ]
        ordering = ["-is_primary", "created_at", "id"]

    def __str__(self):
        return f"{self.name} ({self.relationship})"


class WellnessPreference(models.Model):
    """Lifestyle preferences. allergies and lifestyle_notes are SENSITIVE: admins never see them."""

    class ContactPreference(models.TextChoices):
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"
        SMS = "sms", "SMS"

    class ActivityLevel(models.TextChoices):
        SEDENTARY = "sedentary", "Sedentary"
        LIGHT = "light", "Light"
        MODERATE = "moderate", "Moderate"
        ACTIVE = "active", "Active"

    class DietPreference(models.TextChoices):
        NO_PREFERENCE = "no_preference", "No preference"
        VEGETARIAN = "vegetarian", "Vegetarian"
        VEGAN = "vegan", "Vegan"
        HALAL = "halal", "Halal"
        OTHER = "other", "Other"

    profile = models.OneToOneField(HealthProfile, on_delete=models.CASCADE, related_name="wellness")
    contact_preference = models.CharField(max_length=10, choices=ContactPreference.choices)
    activity_level = models.CharField(max_length=10, choices=ActivityLevel.choices, blank=True, default="")
    diet_preference = models.CharField(max_length=15, choices=DietPreference.choices, blank=True, default="")
    sleep_goal_hours = models.PositiveSmallIntegerField(null=True, blank=True)
    allergies = models.TextField(max_length=500, blank=True, default="")
    lifestyle_notes = models.TextField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(sleep_goal_hours__isnull=True)
                | Q(sleep_goal_hours__gte=4, sleep_goal_hours__lte=12),
                name="wellness_sleep_goal_4_12",
            ),
            models.CheckConstraint(
                condition=Q(contact_preference__in=["email", "phone", "sms"]),
                name="wellness_contact_preference_is_valid",
            ),
        ]

    @property
    def goal_codes(self):
        """The saved goals as a plain list of codes (used by the serializer)."""
        return [g.goal for g in self.goals.all()]

    def __str__(self):
        return f"Wellness of profile {self.profile_id}"


class WellnessGoal(models.Model):
    """One goal code per row; replaces the Week 1 JSON list (that is the normalization step)."""

    class Goal(models.TextChoices):
        BETTER_SLEEP = "better_sleep", "Better sleep"
        MORE_ACTIVITY = "more_activity", "More activity"
        STRESS_MANAGEMENT = "stress_management", "Stress management"
        HEALTHY_EATING = "healthy_eating", "Healthy eating"
        HYDRATION = "hydration", "Hydration"
        WEIGHT_MANAGEMENT = "weight_management", "Weight management"

    # db_index=False: the unique constraint (preference, goal) already starts with preference.
    preference = models.ForeignKey(
        WellnessPreference, on_delete=models.CASCADE, related_name="goals", db_index=False
    )
    goal = models.CharField(max_length=20, choices=Goal.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["preference", "goal"], name="goal_unique_per_preference"),
        ]
        ordering = ["id"]

    def __str__(self):
        return self.goal
