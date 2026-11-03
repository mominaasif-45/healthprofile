from rest_framework import serializers

from .models import AuditEvent


class MemberActivitySerializer(serializers.ModelSerializer):
    """What a member sees about their own activity. No actor (it is always themselves)."""

    class Meta:
        model = AuditEvent
        fields = ["id", "created_at", "action", "target_type", "target_id", "changed_fields", "outcome", "request_id"]
        read_only_fields = fields


class AdminAuditEventSerializer(serializers.ModelSerializer):
    """Admin view of an event. The actor is shown as an id only (no email or name)."""

    class Meta:
        model = AuditEvent
        fields = [
            "id", "created_at", "actor", "actor_role", "action", "target_type", "target_id",
            "changed_fields", "outcome", "request_id",
        ]
        read_only_fields = fields
