"""Phase 2: demographics and wellness sections."""
import pytest

from profiles.models import Demographics, HealthProfile, WellnessGoal

from .conftest import user_login

ROOT = "/api/profiles/me/"
DEMO_URL = ROOT + "demographics/"
WELL_URL = ROOT + "wellness/"


@pytest.fixture
def me(client, user, empty_profile):
    """A signed-in member with an empty profile."""
    user_login(client)
    return client


def pct(user):
    return HealthProfile.objects.get(user=user).completion_percent


# ------------------------------------------------------------------ demographics
@pytest.mark.django_db
def test_demographics_get_is_404_until_saved(me):
    assert me.get(DEMO_URL).status_code == 404


@pytest.mark.django_db
def test_put_demographics_creates_then_replaces(me, user):
    body = {"full_name": "Momina Asif", "preferred_name": "Mo", "age_range": "25-34", "gender": "female", "city": "Lahore"}
    first = me.put(DEMO_URL, body, format="json")
    assert first.status_code == 201 and first.data["city"] == "Lahore"
    assert pct(user) == 25

    second = me.put(DEMO_URL, {"full_name": "Momina A", "age_range": "35-44"}, format="json")
    assert second.status_code == 200
    # PUT replaces the whole section: optional fields that were left out are cleared
    assert (second.data["preferred_name"], second.data["city"], second.data["gender"]) == ("", "", "")


@pytest.mark.django_db
def test_patch_demographics_changes_only_the_sent_fields(me, user):
    me.put(DEMO_URL, {"full_name": "Momina Asif", "age_range": "25-34", "city": "Lahore"}, format="json")
    res = me.patch(DEMO_URL, {"city": "Karachi"}, format="json")
    assert res.status_code == 200
    assert (res.data["city"], res.data["full_name"], res.data["age_range"]) == ("Karachi", "Momina Asif", "25-34")


@pytest.mark.django_db
def test_patch_demographics_is_404_when_section_missing(me):
    assert me.patch(DEMO_URL, {"city": "Lahore"}, format="json").status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    "bad, field",
    [
        ({"full_name": "Momina", "date_of_birth": "2999-01-01"}, "date_of_birth"),  # future
        ({"full_name": "Momina", "date_of_birth": "1800-01-01"}, "date_of_birth"),  # > 120 years ago
        ({"full_name": "Momina", "age_range": "200-300"}, "age_range"),
        ({"full_name": "Momina", "age_range": "25-34", "gender": "robot"}, "gender"),
        ({"full_name": "M", "age_range": "25-34"}, "full_name"),
        ({"full_name": "Momina"}, "age_range"),  # neither dob nor age_range
        ({"age_range": "25-34"}, "full_name"),
    ],
)
def test_demographics_validation_returns_400_with_field_errors(me, bad, field):
    res = me.put(DEMO_URL, bad, format="json")
    assert res.status_code == 400
    assert field in res.json()["error"]["fields"]


@pytest.mark.django_db
def test_patch_cannot_remove_both_dob_and_age_range(me):
    me.put(DEMO_URL, {"full_name": "Momina Asif", "age_range": "25-34"}, format="json")
    res = me.patch(DEMO_URL, {"age_range": None}, format="json")
    assert res.status_code == 400


@pytest.mark.django_db
def test_date_of_birth_alone_is_enough(me):
    assert me.put(DEMO_URL, {"full_name": "Momina Asif", "date_of_birth": "1995-06-15"}, format="json").status_code == 201


@pytest.mark.django_db
def test_demographics_ignores_unknown_and_protected_fields(me, user):
    me.put(DEMO_URL, {"full_name": "Momina Asif", "age_range": "25-34", "role": "admin", "status": "x", "profile": 99}, format="json")
    assert Demographics.objects.get(profile__user=user).profile.user_id == user.id
    user.refresh_from_db()
    assert user.role == "user"


# ------------------------------------------------------------------ wellness
@pytest.mark.django_db
def test_wellness_get_is_404_until_saved(me):
    assert me.get(WELL_URL).status_code == 404


@pytest.mark.django_db
def test_put_wellness_saves_preferences_and_goals(me, user):
    body = {
        "contact_preference": "sms", "activity_level": "light", "diet_preference": "vegan", "sleep_goal_hours": 8,
        "allergies": "Dust", "lifestyle_notes": "Early riser.", "goals": ["better_sleep", "hydration"],
    }
    res = me.put(WELL_URL, body, format="json")
    assert res.status_code == 201
    assert sorted(res.data["goals"]) == ["better_sleep", "hydration"]
    assert pct(user) == 50  # wellness section + at least one goal

    again = me.put(WELL_URL, {"contact_preference": "email"}, format="json")  # PUT without goals = no goals
    assert again.status_code == 200 and again.data["goals"] == []
    assert pct(user) == 25  # only the wellness section remains done


@pytest.mark.django_db
def test_goals_are_replaced_atomically_and_patch_keeps_other_fields(me, user):
    me.put(WELL_URL, {"contact_preference": "email", "allergies": "Dust", "goals": ["better_sleep", "hydration"]}, format="json")
    res = me.patch(WELL_URL, {"goals": ["more_activity"]}, format="json")
    assert res.status_code == 200
    assert res.data["goals"] == ["more_activity"] and res.data["allergies"] == "Dust"
    assert list(WellnessGoal.objects.values_list("goal", flat=True)) == ["more_activity"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "bad, field",
    [
        ({"contact_preference": "pigeon"}, "contact_preference"),
        ({"contact_preference": "email", "activity_level": "olympic"}, "activity_level"),
        ({"contact_preference": "email", "diet_preference": "carnivore"}, "diet_preference"),
        ({"contact_preference": "email", "sleep_goal_hours": 3}, "sleep_goal_hours"),
        ({"contact_preference": "email", "sleep_goal_hours": 13}, "sleep_goal_hours"),
        ({"contact_preference": "email", "allergies": "x" * 501}, "allergies"),
        ({"contact_preference": "email", "lifestyle_notes": "x" * 501}, "lifestyle_notes"),
        ({"contact_preference": "email", "goals": ["fly"]}, "goals"),
        ({"contact_preference": "email", "goals": ["hydration", "hydration"]}, "goals"),
        ({"goals": ["hydration"]}, "contact_preference"),  # required on PUT
    ],
)
def test_wellness_validation_returns_400_with_field_errors(me, bad, field):
    res = me.put(WELL_URL, bad, format="json")
    assert res.status_code == 400
    assert field in res.json()["error"]["fields"] or any(k.startswith(field) for k in res.json()["error"]["fields"])


@pytest.mark.django_db
def test_sleep_goal_boundaries_are_accepted(me):
    for hours in (4, 12):
        assert me.put(WELL_URL, {"contact_preference": "email", "sleep_goal_hours": hours}, format="json").status_code in (200, 201)


# ------------------------------------------------------------------ whole journey
@pytest.mark.django_db
def test_four_sections_reach_100_complete(me, user):
    me.put(DEMO_URL, {"full_name": "Momina Asif", "age_range": "25-34"}, format="json")
    me.post(ROOT + "emergency-contacts/", {"name": "Bilal Ahmed", "relationship": "sibling", "phone": "+92 300 0000001"}, format="json")
    me.put(WELL_URL, {"contact_preference": "email", "goals": ["hydration"]}, format="json")
    whole = me.get(ROOT).data
    assert (whole["completion"]["percent"], whole["completion"]["status"], whole["completion"]["missing"]) == (100, "complete", [])
