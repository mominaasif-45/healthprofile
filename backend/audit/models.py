from django.conf import settings
from django.db import models


class AppendOnlyError(Exception):
    """Raised when code tries to change or remove an audit event that was already written."""


class AuditEventQuerySet(models.QuerySet):
    # Blocking these on the queryset means no ORM shortcut can rewrite history.
    # (Deleting a User still works: Django's SET_NULL on actor uses a low-level update.)
    def update(self, **kwargs):
        raise AppendOnlyError("Audit events are append-only: update() is not allowed.")

    def delete(self):
        raise AppendOnlyError("Audit events are append-only: delete() is not allowed.")


class AuditEvent(models.Model):
    """
    One row per member write or admin action. It stores WHO did WHAT to WHICH object and
    the NAMES of the fields that changed. It never stores values, passwords, tokens, cookies,
    session keys, request bodies, search terms or IP addresses.
    """

    class Action(models.TextChoices):
        PROFILE_CREATED = "profile.created", "Profile created"
        PROFILE_UPDATED = "profile.updated", "Profile updated"
        PROFILE_DELETED = "profile.deleted", "Profile deleted"
        DEMOGRAPHICS_UPDATED = "demographics.updated", "Demographics updated"
        WELLNESS_UPDATED = "wellness.updated", "Wellness updated"
        GOALS_UPDATED = "goals.updated", "Goals updated"
        CONTACT_CREATED = "emergency_contact.created", "Emergency contact created"
        CONTACT_UPDATED = "emergency_contact.updated", "Emergency contact updated"
        CONTACT_DELETED = "emergency_contact.deleted", "Emergency contact deleted"
        ADMIN_LOGIN = "admin.login", "Admin login"
        ADMIN_LOGIN_FAILED = "admin.login_failed", "Admin login failed"
        ADMIN_LOGOUT = "admin.logout", "Admin logout"
        ADMIN_PROFILE_VIEWED = "admin.profile_viewed", "Admin viewed a profile"
        ADMIN_PROFILE_DEACTIVATED = "admin.profile_deactivated", "Admin deactivated a profile"
        ADMIN_PROFILE_REACTIVATED = "admin.profile_reactivated", "Admin reactivated a profile"

    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        DENIED = "denied", "Denied"
        FAILED = "failed", "Failed"

    created_at = models.DateTimeField(auto_now_add=True)
    # SET_NULL: the history survives even if the user account is deleted later.
    # db_index=False: audit_actor_created_idx below already starts with actor, so Django's
    # automatic single-column index on actor_id would be a redundant second index to maintain.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        db_index=False,
    )
    actor_role = models.CharField(max_length=10)  # snapshot: user | admin | anonymous
    action = models.CharField(max_length=40, choices=Action.choices)
    target_type = models.CharField(max_length=30, blank=True, default="")
    target_id = models.BigIntegerField(null=True, blank=True)
    changed_fields = models.JSONField(default=list, blank=True)  # field NAMES only
    request_id = models.UUIDField(null=True, blank=True)
    outcome = models.CharField(max_length=10, choices=Outcome.choices, default=Outcome.SUCCESS)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        indexes = [
            # (a) Query: "this person's recent activity, newest first"
            #     WHERE actor_id = %s ORDER BY created_at DESC
            #     Serves the member's /activity page and the admin filter ?actor=<id>.
            models.Index(fields=["actor", "-created_at"], name="audit_actor_created_idx"),
            # (b) Query: "the history of this profile, newest first"
            #     WHERE target_type = %s AND target_id = %s ORDER BY created_at DESC
            #     Serves the admin profile page (/api/admin/profiles/{id}/audit-events/).
            models.Index(fields=["target_type", "target_id", "-created_at"], name="audit_target_created_idx"),
        ]
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("Audit events are append-only: an existing event cannot be saved again.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Audit events are append-only: delete() is not allowed.")

    def __str__(self):
        return f"{self.action} ({self.outcome})"
