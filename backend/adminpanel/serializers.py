from rest_framework import serializers

from profiles.models import HealthProfile
from profiles.serializers import ProfileSerializer


class AdminProfileListSerializer(serializers.ModelSerializer):
    """One row of the admin table."""

    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = HealthProfile
        fields = [
            "id",
            "full_name",
            "email",
            "age_range",
            "contact_preference",
            "wellness_goals",
            "allergies",
            "emergency_contact_name",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AdminProfileDetailSerializer(ProfileSerializer):
    """Everything about one profile, read-only, plus the owner's account details."""

    email = serializers.EmailField(source="user.email", read_only=True)
    account_name = serializers.CharField(source="user.name", read_only=True)
    member_since = serializers.DateTimeField(source="user.date_joined", read_only=True)

    class Meta(ProfileSerializer.Meta):
        fields = ProfileSerializer.Meta.fields + ["email", "account_name", "member_since"]
        read_only_fields = fields
