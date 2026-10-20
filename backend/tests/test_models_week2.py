"""Phase 1: database constraints, completion rules and the Week 1 -> Week 2 data migration."""
import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from profiles import services
from profiles.models import (
    Demographics,
    EmergencyContact,
    HealthProfile,
    WellnessGoal,
    WellnessPreference,
)

from .conftest import make_profile


# ------------------------------------------------------------------ constraints (IntegrityError)
@pytest.mark.django_db
def test_duplicate_goal_is_rejected(profile):
    preference = profile.wellness
    with pytest.raises(IntegrityError), transaction.atomic():
        WellnessGoal.objects.create(preference=preference, goal="better_sleep")  # already saved by make_profile


@pytest.mark.django_db
def test_same_phone_twice_in_one_profile_is_rejected(profile):
    with pytest.raises(IntegrityError), transaction.atomic():
        EmergencyContact.objects.create(profile=profile, name="Other", relationship="friend", phone="+92 300 1234567")


@pytest.mark.django_db
def test_same_phone_is_allowed_on_different_profiles(profile, other_user):
    second = make_profile(other_user, sections=())
    EmergencyContact.objects.create(profile=second, name="Sana", relationship="friend", phone="+92 300 1234567")
    assert EmergencyContact.objects.filter(phone="+92 300 1234567").count() == 2


@pytest.mark.django_db
def test_two_primary_contacts_are_rejected(profile):
    with pytest.raises(IntegrityError), transaction.atomic():
        EmergencyContact.objects.create(
            profile=profile, name="Second", relationship="friend", phone="+92 300 7654321", is_primary=True
        )


@pytest.mark.django_db
def test_completion_percent_over_100_is_rejected(profile):
    with pytest.raises(IntegrityError), transaction.atomic():
        HealthProfile.objects.filter(pk=profile.pk).update(completion_percent=101)


@pytest.mark.django_db
def test_demographics_needs_dob_or_age_range(empty_profile):
    with pytest.raises(IntegrityError), transaction.atomic():
        Demographics.objects.create(profile=empty_profile, full_name="No Age")


@pytest.mark.django_db
@pytest.mark.parametrize("hours", [3, 13])
def test_sleep_goal_out_of_range_is_rejected(empty_profile, hours):
    with pytest.raises(IntegrityError), transaction.atomic():
        WellnessPreference.objects.create(profile=empty_profile, contact_preference="email", sleep_goal_hours=hours)


@pytest.mark.django_db
def test_sleep_goal_boundaries_are_allowed(empty_profile):
    pref = WellnessPreference.objects.create(profile=empty_profile, contact_preference="sms", sleep_goal_hours=4)
    pref.sleep_goal_hours = 12
    pref.save()


@pytest.mark.django_db
def test_each_user_has_at_most_one_profile(profile, user):
    with pytest.raises(IntegrityError), transaction.atomic():
        HealthProfile.objects.create(user=user)


@pytest.mark.django_db
def test_deleting_profile_deletes_every_section(profile):
    profile_id = profile.pk
    profile.delete()
    assert not Demographics.objects.filter(profile_id=profile_id).exists()
    assert not EmergencyContact.objects.filter(profile_id=profile_id).exists()
    assert not WellnessPreference.objects.filter(profile_id=profile_id).exists()
    assert WellnessGoal.objects.count() == 0


# ------------------------------------------------------------------ completion rules
@pytest.mark.django_db
def test_empty_profile_is_0_percent_not_started(empty_profile):
    services.recalculate_completion(empty_profile)
    empty_profile.refresh_from_db()
    assert (empty_profile.completion_percent, empty_profile.completion_status) == (0, "not_started")


@pytest.mark.django_db
def test_demographics_only_is_25_percent_in_progress(user):
    p = make_profile(user, sections=("demographics",))
    assert (p.completion_percent, p.completion_status) == (25, "in_progress")


@pytest.mark.django_db
def test_all_four_sections_is_100_percent_complete(profile):
    assert (profile.completion_percent, profile.completion_status) == (100, "complete")


@pytest.mark.django_db
def test_wellness_without_goals_is_not_a_fourth_section(user):
    p = make_profile(user, sections=("demographics", "contact", "wellness"))
    assert p.completion_percent == 75


@pytest.mark.django_db
def test_deleting_the_last_contact_drops_back_to_75(profile):
    services.delete_contact(profile.emergency_contacts.get())
    profile.refresh_from_db()
    assert (profile.completion_percent, profile.completion_status) == (75, "in_progress")


# ------------------------------------------------------------------ data migration (Week 1 -> Week 2)
@pytest.mark.django_db(transaction=True)
def test_week1_rows_are_copied_into_the_new_tables(user):
    """Go back to the Week 1 schema, create an old-style row, migrate forward, check the new tables."""
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes("profiles")
    try:
        executor.migrate([("profiles", "0001_initial")])
        old_apps = MigrationExecutor(connection).loader.project_state([("profiles", "0001_initial")]).apps
        Old = old_apps.get_model("profiles", "HealthProfile")
        Old.objects.create(
            user_id=user.pk, full_name="Momina Asif", age_range="25-34", contact_preference="phone",
            wellness_goals=["Sleep 7+ hours", "Reduce stress", "Something unknown"], allergies="Peanuts",
            emergency_contact_name="Bilal Ahmed", emergency_contact_phone="+92 300 0000000",
            lifestyle_notes="Desk job.",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(latest)

        profile = HealthProfile.objects.get(user=user)
        assert profile.demographics.full_name == "Momina Asif"
        assert profile.demographics.age_range == "25-34"
        contact = profile.emergency_contacts.get()
        assert (contact.name, contact.phone, contact.is_primary) == ("Bilal Ahmed", "+92 300 0000000", True)
        assert profile.wellness.contact_preference == "phone"
        assert profile.wellness.allergies == "Peanuts"
        assert sorted(profile.wellness.goal_codes) == ["better_sleep", "stress_management"]  # unknown label skipped
        assert (profile.completion_percent, profile.completion_status) == (100, "complete")
    finally:
        MigrationExecutor(connection).migrate(latest)  # always leave the schema at the latest state
