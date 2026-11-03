"""
Phone numbers are normalised to ONE canonical form before validation, storage and duplicate checks:
an optional leading "+" followed by 7 to 15 digits, e.g. "+92 (300) 123-4567" -> "+923001234567".
All numbers are fictional.
"""
import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from profiles.models import EmergencyContact

from .conftest import make_profile, user_login

URL = "/api/profiles/me/emergency-contacts/"


@pytest.fixture
def me(client, user, empty_profile):
    user_login(client)
    return client


def add(client, phone, name="Contact Person"):
    return client.post(URL, {"name": name, "relationship": "friend", "phone": phone}, format="json")


# ------------------------------------------------------------------ validation of punctuation-heavy input
@pytest.mark.django_db
@pytest.mark.parametrize("bad", [
    "1------",            # 1 digit hidden behind punctuation (passed the old pattern)
    "((((1))))",
    "+-----1",
    "--- --- ---",        # no digits at all
    "+92 300+1234567",    # "+" only allowed at the start
    "+92 300 CALL ME",    # letters
    "123456",             # 6 digits: one too few
    "1234567890123456",   # 16 digits: one too many
])
def test_invalid_phone_is_rejected(me, bad):
    res = add(me, bad)
    assert res.status_code == 400
    assert "phone" in res.json()["error"]["fields"]
    assert EmergencyContact.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("given, stored", [
    ("+92 (300) 123-4567", "+923001234567"),
    ("  +92-300-1234567  ", "+923001234567"),
    ("1234567", "1234567"),                      # 7 digits: the minimum
    ("+123 456 789 012 345", "+123456789012345"),  # 15 digits: the maximum
])
def test_valid_phone_is_stored_in_canonical_form(me, given, stored):
    res = add(me, given)
    assert res.status_code == 201
    assert res.data["phone"] == stored
    assert EmergencyContact.objects.get().phone == stored


# ------------------------------------------------------------------ duplicates in any format
@pytest.mark.django_db
@pytest.mark.parametrize("same_number", ["+92-300-123-4567", "+92 (300) 1234567", "+923001234567"])
def test_equivalent_format_of_a_saved_number_is_a_duplicate(me, same_number):
    assert add(me, "+92 300 1234567", name="First Person").status_code == 201

    res = add(me, same_number, name="Second Person")

    assert res.status_code == 400
    assert "phone" in res.json()["error"]["fields"]
    assert EmergencyContact.objects.count() == 1


@pytest.mark.django_db
def test_patch_to_another_contacts_number_in_a_new_format_is_rejected(me):
    add(me, "+92 300 1234567", name="First Person")
    second = add(me, "+92 300 7654321", name="Second Person").data

    res = me.patch(f"{URL}{second['id']}/", {"phone": "+92 (300) 123-4567"}, format="json")

    assert res.status_code == 400
    assert "phone" in res.json()["error"]["fields"]
    assert EmergencyContact.objects.get(pk=second["id"]).phone == "+923007654321"


@pytest.mark.django_db
def test_patch_with_own_number_reformatted_is_not_a_duplicate(me):
    first = add(me, "+92 300 1234567").data

    res = me.patch(f"{URL}{first['id']}/", {"phone": "+92-300-123-4567"}, format="json")

    assert res.status_code == 200
    assert res.data["phone"] == "+923001234567"


# ------------------------------------------------------------------ the fourth-contact boundary
@pytest.mark.django_db
@pytest.mark.parametrize("fourth", ["+92 300 0000004", "+92-300-000-0001"])  # new number / reformatted duplicate
def test_fourth_contact_is_rejected_whatever_its_format(me, fourth):
    for n in (1, 2, 3):
        assert add(me, f"+92 300 000000{n}", name=f"Person Number{n}").status_code == 201

    res = add(me, fourth, name="Person Four")

    assert res.status_code == 400
    assert "emergency_contacts" in res.json()["error"]["fields"]  # the limit is checked first
    assert EmergencyContact.objects.count() == 3


# ------------------------------------------------------------------ database backstop
@pytest.mark.django_db
@pytest.mark.parametrize("raw", ["+92 300 1234567", "1------", "123456"])
def test_database_rejects_a_non_canonical_phone(user, raw):
    profile = make_profile(user, sections=())
    with pytest.raises(IntegrityError), transaction.atomic():
        EmergencyContact.objects.create(profile=profile, name="Direct Insert", relationship="friend", phone=raw)


# ------------------------------------------------------------------ data migration of stored numbers
def _migrate_to(target):
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return MigrationExecutor(connection).loader.project_state(target).apps


@pytest.mark.django_db(transaction=True)
def test_migration_rewrites_stored_numbers_to_canonical_form(user, other_user):
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes("profiles")
    try:
        old = _migrate_to([("profiles", "0006_restore_one_primary_contact_constraint")])
        Profile, Contact = old.get_model("profiles", "HealthProfile"), old.get_model("profiles", "EmergencyContact")
        mine, theirs = Profile.objects.create(user_id=user.pk), Profile.objects.create(user_id=other_user.pk)
        Contact.objects.create(profile=mine, name="A", relationship="friend", phone="+92 300 1234567", is_primary=True)
        Contact.objects.create(profile=mine, name="B", relationship="friend", phone="+92 300 76543-21")
        # the same digits on a DIFFERENT profile is not a collision
        Contact.objects.create(profile=theirs, name="C", relationship="friend", phone="+92-300-123-4567", is_primary=True)

        _migrate_to(latest)

        phones = sorted(EmergencyContact.objects.values_list("profile__user_id", "phone"))
        assert phones == sorted([
            (user.pk, "+923001234567"), (user.pk, "+923007654321"), (other_user.pk, "+923001234567"),
        ])
    finally:
        EmergencyContact.objects.all().delete()
        _migrate_to(latest)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("second_phone, reason", [
    ("+92-300-123-4567", "same number twice on one profile"),
    ("1------", "outside 7-15 digits"),
])
def test_migration_stops_on_unsafe_rows_and_names_only_ids(user, second_phone, reason):
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes("profiles")
    try:
        old = _migrate_to([("profiles", "0006_restore_one_primary_contact_constraint")])
        Profile, Contact = old.get_model("profiles", "HealthProfile"), old.get_model("profiles", "EmergencyContact")
        profile = Profile.objects.create(user_id=user.pk)
        Contact.objects.create(profile=profile, name="A", relationship="friend", phone="+92 300 1234567", is_primary=True)
        bad = Contact.objects.create(profile=profile, name="B", relationship="friend", phone=second_phone)

        with pytest.raises(Exception) as error:
            _migrate_to(latest)

        message = str(error.value)
        assert str(bad.pk) in message
        assert "1234567" not in message and second_phone not in message  # ids only, never the numbers
        assert Contact.objects.filter(pk=bad.pk, phone=second_phone).exists()  # nothing was changed
    finally:
        old = _migrate_to([("profiles", "0006_restore_one_primary_contact_constraint")])
        old.get_model("profiles", "EmergencyContact").objects.all().delete()
        _migrate_to(latest)
