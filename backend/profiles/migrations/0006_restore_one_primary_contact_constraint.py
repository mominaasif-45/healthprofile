"""
Repair for migration 0005.

When Django removed the redundant automatic index on EmergencyContact.profile_id, it also dropped
our partial unique index "contact_one_primary_per_profile" (it sits on the same single column and
Django's schema editor matched it by column). The model still declared the constraint, so
makemigrations saw no difference. Removing and re-adding it here puts the index back in the database.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0005_drop_redundant_fk_indexes"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP INDEX IF EXISTS contact_one_primary_per_profile",
            reverse_sql=migrations.RunSQL.noop,
            state_operations=[
                migrations.RemoveConstraint(model_name="emergencycontact", name="contact_one_primary_per_profile"),
            ],
        ),
        migrations.AddConstraint(
            model_name="emergencycontact",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_primary", True)),
                fields=("profile",),
                name="contact_one_primary_per_profile",
            ),
        ),
    ]
