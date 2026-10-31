"""
Business rules for profile sections.

Views stay thin: they authenticate, validate with a serializer, call one function
from here, then write one audit event. Every function that changes data runs inside
a transaction and ends with recalculate_completion(), so the stored completion
numbers can never drift from the real data.

Locking policy: every function that changes a profile starts with _lock(), which locks the
profile row and re-checks, on that fresh row, that the profile is still active. Admin
deactivate / reactivate take the same row lock, so the two can never interleave.
"""
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import (
    Demographics,
    EmergencyContact,
    HealthProfile,
    WellnessGoal,
    WellnessPreference,
)
from .phones import normalize_phone

class ProfileDeactivated(Exception):
    """The profile was not active when its row lock was taken, so the write must not happen."""


MAX_CONTACTS = 3
SECTION_WEIGHT = 25  # 4 sections x 25% = 100%

# Defaults used when a PUT omits an optional field (PUT replaces the whole section).
DEMOGRAPHICS_DEFAULTS = {
    "preferred_name": "",
    "date_of_birth": None,
    "age_range": None,
    "gender": "",
    "city": "",
}
WELLNESS_DEFAULTS = {
    "activity_level": "",
    "diet_preference": "",
    "sleep_goal_hours": None,
    "allergies": "",
    "lifestyle_notes": "",
}


# ---------------------------------------------------------------- completion
def completion_checks(profile):
    """The four sections, in order, as (label to show when missing, is_done)."""
    return [
        ("Fill in your demographics", Demographics.objects.filter(profile=profile).exists()),
        ("Add an emergency contact", EmergencyContact.objects.filter(profile=profile).exists()),
        ("Save your wellness preferences", WellnessPreference.objects.filter(profile=profile).exists()),
        ("Pick at least one wellness goal", WellnessGoal.objects.filter(preference__profile=profile).exists()),
    ]


def status_for_percent(percent):
    if percent == 0:
        return HealthProfile.CompletionStatus.NOT_STARTED
    if percent == 100:
        return HealthProfile.CompletionStatus.COMPLETE
    return HealthProfile.CompletionStatus.IN_PROGRESS


def recalculate_completion(profile):
    """Recompute and store completion_percent / completion_status. Returns (percent, status)."""
    done = sum(1 for _, ok in completion_checks(profile) if ok)
    percent = done * SECTION_WEIGHT
    status = status_for_percent(percent)
    HealthProfile.objects.filter(pk=profile.pk).update(
        completion_percent=percent, completion_status=status, updated_at=timezone.now()
    )
    profile.completion_percent, profile.completion_status = percent, status
    return percent, status


def missing_sections(profile):
    return [label for label, ok in completion_checks(profile) if not ok]


# ---------------------------------------------------------------- helpers
def _changed(instance, values):
    """Names of the fields whose value actually differs. Returns names only, never values."""
    return sorted(name for name, value in values.items() if getattr(instance, name) != value)


def _with_canonical_phone(data):
    """Normalise data["phone"] (if sent) so duplicates are found whatever the formatting."""
    if "phone" not in data:
        return data
    try:
        return {**data, "phone": normalize_phone(data["phone"])}
    except ValueError as exc:
        raise ValidationError({"phone": [str(exc)]}) from exc


def _lock(profile):
    """
    Lock the profile row (held until the transaction ends) and return the locked, fresh row.
    If another transaction held the lock, PostgreSQL re-reads the row once it is released, so a
    deactivation that committed while this request waited is seen here and the write is refused.
    """
    locked = HealthProfile.objects.select_for_update().get(pk=profile.pk)
    if locked.status != HealthProfile.Status.ACTIVE:
        raise ProfileDeactivated()
    return locked


# ---------------------------------------------------------------- demographics
@transaction.atomic
def save_demographics(profile, data, replace):
    """
    replace=True  -> PUT: create the section or replace it (omitted optional fields reset).
    replace=False -> PATCH: change only the fields that were sent (section must already exist).
    Returns (demographics, changed_field_names).
    """
    profile = _lock(profile)
    existing = Demographics.objects.filter(profile=profile).first()
    if replace:
        values = {**DEMOGRAPHICS_DEFAULTS, **data}
    else:
        values = dict(data)

    if existing is None:
        instance = Demographics.objects.create(profile=profile, **values)
        changed = sorted(values)
    else:
        changed = _changed(existing, values)
        for name, value in values.items():
            setattr(existing, name, value)
        existing.save()
        instance = existing

    recalculate_completion(profile)
    return instance, changed


# ---------------------------------------------------------------- wellness
@transaction.atomic
def save_wellness(profile, data, replace):
    """
    Save the wellness preference and its goals. Goals arrive as a list of codes and are
    replaced atomically (same transaction as the preference). Returns (preference, changed_names).
    """
    profile = _lock(profile)
    data = dict(data)
    goals = data.pop("goal_codes", None)
    existing = WellnessPreference.objects.filter(profile=profile).first()
    values = {**WELLNESS_DEFAULTS, **data} if replace else dict(data)

    if existing is None:
        instance = WellnessPreference.objects.create(profile=profile, **values)
        changed = sorted(values)
        if goals is None:
            goals = []
    else:
        changed = _changed(existing, values)
        for name, value in values.items():
            setattr(existing, name, value)
        existing.save()
        instance = existing

    if replace and goals is None:
        goals = []  # PUT without goals means "no goals"
    if goals is not None:
        current = list(instance.goals.values_list("goal", flat=True))
        if set(current) != set(goals):
            instance.goals.exclude(goal__in=goals).delete()
            for code in goals:
                if code not in current:
                    WellnessGoal.objects.create(preference=instance, goal=code)
            changed.append("goals")

    recalculate_completion(profile)
    return instance, sorted(changed)


# ---------------------------------------------------------------- root profile
@transaction.atomic
def delete_profile(profile):
    """Delete the profile and (by cascade) every section, under the same lock and status re-check."""
    _lock(profile).delete()


# ---------------------------------------------------------------- emergency contacts
@transaction.atomic
def create_contact(profile, data):
    data = _with_canonical_phone(data)
    profile = _lock(profile)
    contacts = EmergencyContact.objects.filter(profile=profile)
    if contacts.count() >= MAX_CONTACTS:
        raise ValidationError({"emergency_contacts": [f"You can save at most {MAX_CONTACTS} emergency contacts."]})
    if contacts.filter(phone=data["phone"]).exists():
        raise ValidationError({"phone": ["This phone number is already saved on your profile."]})

    make_primary = bool(data.get("is_primary")) or not contacts.exists()  # the first contact is primary
    if make_primary:
        contacts.filter(is_primary=True).update(is_primary=False)
    contact = EmergencyContact.objects.create(profile=profile, **{**data, "is_primary": make_primary})
    recalculate_completion(profile)
    return contact


@transaction.atomic
def update_contact(contact, data):
    data = _with_canonical_phone(data)
    profile = _lock(contact.profile)
    contacts = EmergencyContact.objects.filter(profile=profile)
    contact = contacts.get(pk=contact.pk)
    if "phone" in data and contacts.exclude(pk=contact.pk).filter(phone=data["phone"]).exists():
        raise ValidationError({"phone": ["This phone number is already saved on your profile."]})

    changed = _changed(contact, data)
    if data.get("is_primary"):
        contacts.exclude(pk=contact.pk).filter(is_primary=True).update(is_primary=False)
    for name, value in data.items():
        setattr(contact, name, value)
    contact.save()
    recalculate_completion(profile)
    return contact, changed


@transaction.atomic
def delete_contact(contact):
    profile = _lock(contact.profile)
    was_primary = contact.is_primary
    EmergencyContact.objects.filter(pk=contact.pk).delete()
    if was_primary:  # keep one primary: promote the oldest remaining contact
        heir = EmergencyContact.objects.filter(profile=profile).order_by("created_at", "id").first()
        if heir is not None:
            EmergencyContact.objects.filter(pk=heir.pk).update(is_primary=True)
    recalculate_completion(profile)
