"""
Rewrite every stored emergency-contact phone into canonical form ("+92 300 1234567" -> "+923001234567"),
so migration 0008 can add the CHECK constraint and the (profile, phone) unique constraint also
catches the same number typed differently.

It checks everything BEFORE changing anything. It stops (and changes nothing) if a row is not a
valid 7-15 digit number, or if two contacts on one profile would become the same number. The
error names contact ids only, never the numbers. Nothing is deleted or merged automatically.

The rule is copied here on purpose: a migration must keep working even if profiles/phones.py changes.
Reversing does nothing: the original spacing cannot be recovered and the canonical form is still valid.
"""
import re
from collections import defaultdict

from django.db import migrations

ALLOWED_INPUT = re.compile(r"^\+?[0-9 ()\-]+$")
MIN_DIGITS, MAX_DIGITS = 7, 15


def canonical(phone):
    value = (phone or "").strip()
    digits = re.sub(r"\D", "", value)
    if not ALLOWED_INPUT.match(value) or not MIN_DIGITS <= len(digits) <= MAX_DIGITS:
        return None
    return ("+" if value.startswith("+") else "") + digits


def normalize_phones(apps, schema_editor):
    EmergencyContact = apps.get_model("profiles", "EmergencyContact")
    rows = list(EmergencyContact.objects.order_by("id").values_list("id", "profile_id", "phone"))

    invalid, groups, changes = [], defaultdict(list), []
    for pk, profile_id, phone in rows:
        new = canonical(phone)
        if new is None:
            invalid.append(pk)
            continue
        groups[(profile_id, new)].append(pk)
        if new != phone:
            changes.append((pk, new))
    collisions = sorted(pk for ids in groups.values() if len(ids) > 1 for pk in ids)

    if invalid or collisions:
        raise RuntimeError(
            "Cannot normalise emergency-contact phones; fix these rows by hand first. "
            f"Not a valid 7-15 digit number: contact ids {invalid}. "
            f"Same number twice on one profile: contact ids {collisions}."
        )
    for pk, new in changes:
        EmergencyContact.objects.filter(pk=pk).update(phone=new)


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0006_restore_one_primary_contact_constraint"),
    ]

    operations = [
        migrations.RunPython(normalize_phones, migrations.RunPython.noop),
    ]
