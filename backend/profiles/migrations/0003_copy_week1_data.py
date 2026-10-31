"""
Data migration: copy the Week 1 single-table profile into the new section tables.

Forward: for every existing HealthProfile row it creates
  - Demographics   (full_name, date_of_birth, age_range)
  - EmergencyContact (only if both name and phone were filled in; relationship "other", primary)
  - WellnessPreference (contact_preference, allergies, lifestyle_notes)
  - WellnessGoal   (the old free-text goal labels that match a known goal; unknown labels are skipped)
and computes completion_percent / completion_status.

Reverse: copies the section data back into the old columns, so migration 0004 can be undone
without losing information that still fits in the old shape (a profile with several contacts
keeps its primary one; goals are written back as readable labels).
"""
from django.db import migrations

# Week 1 stored goals as free-text labels; map the known ones to the new goal codes.
LABEL_TO_CODE = {
    "sleep 7+ hours": "better_sleep",
    "walk 8,000 steps": "more_activity",
    "stretch daily": "more_activity",
    "reduce stress": "stress_management",
    "meditate 10 minutes": "stress_management",
    "more vegetables": "healthy_eating",
    "cut back on sugar": "healthy_eating",
    "drink more water": "hydration",
}
CODE_TO_LABEL = {
    "better_sleep": "Sleep 7+ hours",
    "more_activity": "Walk 8,000 steps",
    "stress_management": "Reduce stress",
    "healthy_eating": "More vegetables",
    "hydration": "Drink more water",
    "weight_management": "Weight management",
}
VALID_CODES = set(CODE_TO_LABEL)


def _completion(percent):
    if percent == 0:
        return "not_started"
    return "complete" if percent == 100 else "in_progress"


def copy_forward(apps, schema_editor):
    HealthProfile = apps.get_model("profiles", "HealthProfile")
    Demographics = apps.get_model("profiles", "Demographics")
    EmergencyContact = apps.get_model("profiles", "EmergencyContact")
    WellnessPreference = apps.get_model("profiles", "WellnessPreference")
    WellnessGoal = apps.get_model("profiles", "WellnessGoal")

    for profile in HealthProfile.objects.all():
        sections = 0

        full_name = (profile.full_name or "").strip()[:120]
        if full_name and (profile.date_of_birth or profile.age_range):
            Demographics.objects.get_or_create(
                profile=profile,
                defaults=dict(
                    full_name=full_name,
                    date_of_birth=profile.date_of_birth,
                    age_range=profile.age_range,
                ),
            )
            sections += 1

        name = (profile.emergency_contact_name or "").strip()
        phone = (profile.emergency_contact_phone or "").strip()
        if name and phone:
            EmergencyContact.objects.get_or_create(
                profile=profile,
                phone=phone,
                defaults=dict(name=name[:120], relationship="other", is_primary=True),
            )
            sections += 1

        preference, _ = WellnessPreference.objects.get_or_create(
            profile=profile,
            defaults=dict(
                contact_preference=profile.contact_preference or "email",
                allergies=(profile.allergies or "")[:500],
                lifestyle_notes=(profile.lifestyle_notes or "")[:500],
            ),
        )
        sections += 1

        codes = []
        for label in profile.wellness_goals or []:
            key = str(label).strip().lower()
            code = LABEL_TO_CODE.get(key, key if key in VALID_CODES else None)
            if code and code not in codes:
                codes.append(code)
        for code in codes:
            WellnessGoal.objects.get_or_create(preference=preference, goal=code)
        if codes:
            sections += 1

        percent = sections * 25
        HealthProfile.objects.filter(pk=profile.pk).update(
            completion_percent=percent, completion_status=_completion(percent)
        )


def copy_backward(apps, schema_editor):
    HealthProfile = apps.get_model("profiles", "HealthProfile")

    for profile in HealthProfile.objects.all():
        values = {}
        demographics = getattr(profile, "demographics", None)
        if demographics is not None:
            values.update(
                full_name=demographics.full_name,
                date_of_birth=demographics.date_of_birth,
                age_range=demographics.age_range,
            )
        contact = profile.emergency_contacts.order_by("-is_primary", "id").first()
        if contact is not None:
            values.update(emergency_contact_name=contact.name, emergency_contact_phone=contact.phone)
        wellness = getattr(profile, "wellness", None)
        if wellness is not None:
            values.update(
                contact_preference=wellness.contact_preference,
                allergies=wellness.allergies,
                lifestyle_notes=wellness.lifestyle_notes,
                wellness_goals=[CODE_TO_LABEL.get(g.goal, g.goal) for g in wellness.goals.all()],
            )
        if values:
            HealthProfile.objects.filter(pk=profile.pk).update(**values)


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0002_week2_sections"),
    ]

    operations = [
        migrations.RunPython(copy_forward, copy_backward),
    ]
