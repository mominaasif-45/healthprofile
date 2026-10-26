import re

from django.utils import timezone
from rest_framework import serializers

from .models import HealthProfile

PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 ()\-]{6,23}$")
MAX_GOALS = 10
MAX_GOAL_LENGTH = 60


class ProfileSerializer(serializers.ModelSerializer):
    """The owner's view of their own profile (also used for create and update)."""

    completeness = serializers.SerializerMethodField()

    class Meta:
        model = HealthProfile
        fields = [
            "id",
            "full_name",
            "date_of_birth",
            "age_range",
            "contact_preference",
            "wellness_goals",
            "allergies",
            "emergency_contact_name",
            "emergency_contact_phone",
            "lifestyle_notes",
            "status",
            "completeness",
            "created_at",
            "updated_at",
        ]
        # status is changed only by an admin, never by the owner
        read_only_fields = ["id", "status", "created_at", "updated_at"]
        extra_kwargs = {
            "allergies": {"max_length": 500, "allow_blank": True, "required": False},
            "lifestyle_notes": {"max_length": 1000, "allow_blank": True, "required": False},
            "emergency_contact_name": {"allow_blank": True, "required": False},
            "emergency_contact_phone": {"allow_blank": True, "required": False},
        }

    # ---------- field validation ----------
    def validate_full_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Full name must be at least 2 characters.")
        return value

    def validate_date_of_birth(self, value):
        if value is not None and value > timezone.localdate():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value

    def validate_wellness_goals(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Wellness goals must be a list.")
        cleaned = []
        for goal in value:
            if not isinstance(goal, str):
                raise serializers.ValidationError("Each goal must be text.")
            goal = goal.strip()
            if not goal:
                continue
            if len(goal) > MAX_GOAL_LENGTH:
                raise serializers.ValidationError(
                    f"Each goal must be at most {MAX_GOAL_LENGTH} characters."
                )
            if goal.lower() not in [g.lower() for g in cleaned]:
                cleaned.append(goal)
        if len(cleaned) > MAX_GOALS:
            raise serializers.ValidationError(f"Choose at most {MAX_GOALS} goals.")
        return cleaned

    def validate_emergency_contact_phone(self, value):
        value = value.strip()
        if value and not PHONE_PATTERN.match(value):
            raise serializers.ValidationError("Enter a valid phone number, e.g. +92 300 0000000.")
        return value

    def validate_emergency_contact_name(self, value):
        return value.strip()

    # ---------- cross-field validation ----------
    def validate(self, attrs):
        # On PATCH, fall back to the stored values for fields that weren't sent.
        def effective(name):
            if name in attrs:
                return attrs[name]
            return getattr(self.instance, name, None) if self.instance else None

        if not effective("date_of_birth") and not effective("age_range"):
            raise serializers.ValidationError(
                {"age_range": ["Provide an age range or a date of birth."]}
            )
        return attrs

    # ---------- computed ----------
    def get_completeness(self, obj):
        """Profile strength shown on the profile page: 5 checks, 20% each."""
        checks = [
            ("Add your full name", bool(obj.full_name)),
            # Either one is enough: they are alternatives, not both required.
            (
                "Add your date of birth or age range",
                obj.date_of_birth is not None or bool(obj.age_range),
            ),
            ("Pick at least one wellness goal", bool(obj.wellness_goals)),
            (
                "Add an emergency contact",
                bool(obj.emergency_contact_name and obj.emergency_contact_phone),
            ),
            ("Add lifestyle notes or allergies", bool(obj.lifestyle_notes or obj.allergies)),
        ]
        done = sum(1 for _, ok in checks if ok)
        missing = [label for label, ok in checks if not ok]
        return {"percent": done * 20, "missing": missing}
