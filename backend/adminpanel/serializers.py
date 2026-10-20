"""
Admin-facing serializers. They are written as an ALLOW-LIST: a field is visible only if it is
listed here. That is why the list and detail serializers are separate classes from the member
ones, and why a new column added to a model later cannot leak to admins by accident.

Never shown to admins: date_of_birth, allergies, lifestyle_notes, full phone numbers,
password hashes, tokens, is_staff / is_superuser / last_login.
"""
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from audit.models import AuditEvent
from profiles.models import HealthProfile

# ------------------------------------------------------------------ helpers
AGE_BUCKETS = [(18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 54, "45-54"), (55, 64, "55-64")]


def age_range_for(demographics):
    """Show the saved age range, or derive one from the date of birth (the date itself is never shown)."""
    if demographics.age_range:
        return demographics.age_range
    dob = demographics.date_of_birth
    if dob is None:
        return None
    today = timezone.localdate()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < 18:
        return "under 18"
    for low, high, label in AGE_BUCKETS:
        if low <= age <= high:
            return label
    return "65+"


def mask_phone(phone):
    """'+92 300 4521' -> '•••• •••• 4521' (only the last 4 digits survive)."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"•••• •••• {digits[-4:]}" if len(digits) >= 4 else "••••"


def display_name(profile):
    demographics = getattr(profile, "demographics", None)
    if demographics is not None:
        return demographics.preferred_name or demographics.full_name
    return profile.user.name


# ------------------------------------------------------------------ nested shapes (documentation only)
class AdminDemographicsSerializer(serializers.Serializer):
    full_name = serializers.CharField()
    preferred_name = serializers.CharField()
    age_range = serializers.CharField(allow_null=True, help_text="Saved range, or derived from the date of birth")
    gender = serializers.CharField()
    city = serializers.CharField()


class AdminContactSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    relationship = serializers.CharField()
    phone_masked = serializers.CharField(help_text="Only the last 4 digits, e.g. '•••• •••• 4521'")
    is_primary = serializers.BooleanField()


class AdminWellnessSerializer(serializers.Serializer):
    contact_preference = serializers.CharField()
    activity_level = serializers.CharField()
    diet_preference = serializers.CharField()
    sleep_goal_hours = serializers.IntegerField(allow_null=True)
    goals = serializers.ListField(child=serializers.CharField())
    has_allergies = serializers.BooleanField(help_text="Yes/no only. The allergy text is never exposed")


# ------------------------------------------------------------------ profiles
class AdminProfileListSerializer(serializers.ModelSerializer):
    """One row of the admin table. Nothing beyond these 7 fields."""

    display_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = HealthProfile
        fields = ["id", "display_name", "email", "status", "completion_status", "completion_percent", "created_at"]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_display_name(self, obj):
        return display_name(obj)


class AdminProfileDetailSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)
    demographics = serializers.SerializerMethodField()
    emergency_contacts = serializers.SerializerMethodField()
    wellness = serializers.SerializerMethodField()

    class Meta:
        model = HealthProfile
        fields = [
            "id", "display_name", "email", "status", "completion_status", "completion_percent",
            "created_at", "updated_at", "demographics", "emergency_contacts", "wellness",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_display_name(self, obj):
        return display_name(obj)

    @extend_schema_field(AdminDemographicsSerializer(allow_null=True))
    def get_demographics(self, obj):
        d = getattr(obj, "demographics", None)
        if d is None:
            return None
        return {
            "full_name": d.full_name,
            "preferred_name": d.preferred_name,
            "age_range": age_range_for(d),  # no date_of_birth
            "gender": d.gender,
            "city": d.city,
        }

    @extend_schema_field(AdminContactSerializer(many=True))
    def get_emergency_contacts(self, obj):
        return [
            {
                "id": c.id,
                "name": c.name,
                "relationship": c.relationship,
                "phone_masked": mask_phone(c.phone),  # never the full number
                "is_primary": c.is_primary,
            }
            for c in obj.emergency_contacts.all()
        ]

    @extend_schema_field(AdminWellnessSerializer(allow_null=True))
    def get_wellness(self, obj):
        w = getattr(obj, "wellness", None)
        if w is None:
            return None
        return {
            "contact_preference": w.contact_preference,
            "activity_level": w.activity_level,
            "diet_preference": w.diet_preference,
            "sleep_goal_hours": w.sleep_goal_hours,
            "goals": [g.goal for g in w.goals.all()],
            "has_allergies": bool(w.allergies.strip()),  # a yes/no only, never the text
            # lifestyle_notes and allergies are deliberately not exposed
        }


# ------------------------------------------------------------------ query parameters
class DateRangeQuerySerializer(serializers.Serializer):
    """Validates ?created_after / ?created_before (YYYY-MM-DD). Bad input becomes a 400 with field errors."""

    created_after = serializers.DateField(required=False)
    created_before = serializers.DateField(required=False)

    def validate(self, attrs):
        after, before = attrs.get("created_after"), attrs.get("created_before")
        if after and before and after > before:
            raise serializers.ValidationError({"created_after": ["Must be on or before created_before."]})
        return attrs


class AdminProfileQuerySerializer(DateRangeQuerySerializer):
    ORDERINGS = ["created_at", "-created_at", "completion_percent", "-completion_percent"]

    search = serializers.CharField(required=False, allow_blank=True, max_length=100)
    status = serializers.ChoiceField(choices=HealthProfile.Status.choices, required=False)
    completion_status = serializers.ChoiceField(choices=HealthProfile.CompletionStatus.choices, required=False)
    ordering = serializers.ChoiceField(choices=ORDERINGS, required=False)


class AuditEventQuerySerializer(DateRangeQuerySerializer):
    action = serializers.ChoiceField(choices=AuditEvent.Action.choices, required=False)
    actor = serializers.IntegerField(required=False, min_value=1)
    outcome = serializers.ChoiceField(choices=AuditEvent.Outcome.choices, required=False)
