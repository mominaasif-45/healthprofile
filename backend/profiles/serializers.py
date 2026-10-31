from datetime import date

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from . import services
from .models import Demographics, EmergencyContact, HealthProfile, WellnessGoal, WellnessPreference
from .phones import normalize_phone

MAX_AGE_YEARS = 120


class DemographicsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Demographics
        fields = [
            "full_name", "preferred_name", "date_of_birth", "age_range", "gender", "city",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {
            "full_name": {"min_length": 2, "max_length": 120},
            "preferred_name": {"required": False, "allow_blank": True, "max_length": 60},
            "date_of_birth": {"required": False, "allow_null": True},
            "age_range": {"required": False, "allow_null": True},
            "gender": {"required": False, "allow_blank": True},
            "city": {"required": False, "allow_blank": True, "max_length": 80},
        }

    def validate_full_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Full name must be at least 2 characters.")
        return value

    def validate_date_of_birth(self, value):
        if value is None:
            return value
        today = timezone.localdate()
        if value > today:
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        oldest = date(today.year - MAX_AGE_YEARS, today.month, min(today.day, 28))
        if value < oldest:
            raise serializers.ValidationError(f"Date of birth cannot be more than {MAX_AGE_YEARS} years ago.")
        return value

    def validate(self, attrs):
        # On PATCH, values that were not sent come from the saved row.
        def effective(name):
            if name in attrs:
                return attrs[name]
            return getattr(self.instance, name, None) if self.instance else None

        if not effective("date_of_birth") and not effective("age_range"):
            raise serializers.ValidationError({"age_range": ["Provide an age range or a date of birth."]})
        return attrs


class WellnessSerializer(serializers.ModelSerializer):
    # Goals are sent and returned as a list of goal codes, e.g. ["better_sleep", "hydration"].
    goals = serializers.ListField(
        source="goal_codes",
        child=serializers.ChoiceField(choices=WellnessGoal.Goal.choices),
        required=False,
        max_length=len(WellnessGoal.Goal.choices),
    )

    class Meta:
        model = WellnessPreference
        fields = [
            "contact_preference", "activity_level", "diet_preference", "sleep_goal_hours",
            "allergies", "lifestyle_notes", "goals", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {
            "activity_level": {"required": False, "allow_blank": True},
            "diet_preference": {"required": False, "allow_blank": True},
            "sleep_goal_hours": {"required": False, "allow_null": True, "min_value": 4, "max_value": 12},
            "allergies": {"required": False, "allow_blank": True, "max_length": 500},
            "lifestyle_notes": {"required": False, "allow_blank": True, "max_length": 500},
        }

    def validate_goals(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Each goal can only be chosen once.")
        return value


class EmergencyContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyContact
        fields = ["id", "name", "relationship", "phone", "is_primary", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "name": {"min_length": 2, "max_length": 120},
            "is_primary": {"required": False},
        }

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Name must be at least 2 characters.")
        return value

    def validate_phone(self, value):
        # Fictional numbers only. Returns the canonical form ("+923000000000"), which is what is stored.
        try:
            return normalize_phone(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class CompletionSerializer(serializers.Serializer):
    """Shape of the completion object (used for the API docs)."""

    status = serializers.ChoiceField(choices=HealthProfile.CompletionStatus.choices)
    percent = serializers.IntegerField(min_value=0, max_value=100)
    missing = serializers.ListField(child=serializers.CharField(), help_text="Sections still to fill in.")


class ProfileSerializer(serializers.ModelSerializer):
    """The whole profile for its owner: root fields plus every section (or null / empty list)."""

    demographics = serializers.SerializerMethodField()
    emergency_contacts = serializers.SerializerMethodField()
    wellness = serializers.SerializerMethodField()
    completion = serializers.SerializerMethodField()

    class Meta:
        model = HealthProfile
        fields = [
            "id", "status", "completion", "demographics", "emergency_contacts", "wellness",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(DemographicsSerializer(allow_null=True))
    def get_demographics(self, obj):
        section = getattr(obj, "demographics", None)
        return DemographicsSerializer(section).data if section else None

    @extend_schema_field(WellnessSerializer(allow_null=True))
    def get_wellness(self, obj):
        section = getattr(obj, "wellness", None)
        return WellnessSerializer(section).data if section else None

    @extend_schema_field(EmergencyContactSerializer(many=True))
    def get_emergency_contacts(self, obj):
        return EmergencyContactSerializer(obj.emergency_contacts.all(), many=True).data

    @extend_schema_field(CompletionSerializer())
    def get_completion(self, obj):
        return {
            "status": obj.completion_status,
            "percent": obj.completion_percent,
            "missing": services.missing_sections(obj),
        }
