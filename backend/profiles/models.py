from django.conf import settings
from django.db import models
from django.db.models import Q


class HealthProfile(models.Model):
    """
    One wellness profile per user (OneToOne). Deleting the user deletes the
    profile. All data is synthetic: wellness goals only, never diagnoses.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DEACTIVATED = "deactivated", "Deactivated"

    class ContactPreference(models.TextChoices):
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"
        SMS = "sms", "SMS"

    class AgeRange(models.TextChoices):
        R18_24 = "18-24", "18-24"
        R25_34 = "25-34", "25-34"
        R35_44 = "35-44", "35-44"
        R45_54 = "45-54", "45-54"
        R55_64 = "55-64", "55-64"
        R65_PLUS = "65+", "65+"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="health_profile"
    )
    full_name = models.CharField(max_length=150)
    date_of_birth = models.DateField(null=True, blank=True)
    age_range = models.CharField(
        max_length=10, choices=AgeRange.choices, null=True, blank=True
    )
    contact_preference = models.CharField(
        max_length=10, choices=ContactPreference.choices, default=ContactPreference.EMAIL
    )
    # A short list of goal labels, e.g. ["Sleep 7+ hours", "Walk 8,000 steps"]
    wellness_goals = models.JSONField(default=list, blank=True)
    allergies = models.TextField(max_length=500, blank=True, default="")
    emergency_contact_name = models.CharField(max_length=150, blank=True, default="")
    emergency_contact_phone = models.CharField(max_length=25, blank=True, default="")
    lifestyle_notes = models.TextField(max_length=1000, blank=True, default="")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # A profile needs at least a date of birth or an age range.
            models.CheckConstraint(
                condition=Q(date_of_birth__isnull=False) | Q(age_range__isnull=False),
                name="profile_needs_dob_or_age_range",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["active", "deactivated"]),
                name="profile_status_is_valid",
            ),
            models.CheckConstraint(
                condition=Q(contact_preference__in=["email", "phone", "sms"]),
                name="profile_contact_preference_is_valid",
            ),
        ]
        indexes = [
            # Serves the admin list: WHERE status = 'active' ORDER BY created_at DESC
            models.Index(fields=["status", "-created_at"], name="profile_status_created_idx"),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.status})"
