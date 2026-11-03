"""
The primary-contact rule: a profile with at least one emergency contact always has EXACTLY one primary.

  "at most one"  -> the database (partial unique index contact_one_primary_per_profile)
  "at least one" -> the service, under the profile row lock: the first contact becomes primary,
                    deleting the primary promotes the oldest remaining one, and the current primary
                    cannot be unset (choose "Make primary" on another contact instead).
"""
import pytest

from profiles.models import EmergencyContact

from .conftest import make_profile, user_login

URL = "/api/profiles/me/emergency-contacts/"


@pytest.fixture
def me(client, user, empty_profile):
    user_login(client)
    return client


def add(client, n, **extra):
    res = client.post(URL, {"name": f"Contact Number{n}", "relationship": "friend",
                            "phone": f"+92 300 000000{n}", **extra}, format="json")
    assert res.status_code == 201, res.json()
    return res.data


def primaries(profile):
    return list(EmergencyContact.objects.filter(profile=profile, is_primary=True).values_list("id", flat=True))


def assert_invariant(profile):
    """The rule itself: no contacts -> no primary; any contacts -> exactly one primary."""
    count = EmergencyContact.objects.filter(profile=profile).count()
    assert len(primaries(profile)) == (1 if count else 0), f"{count} contacts but primaries={primaries(profile)}"


# ------------------------------------------------------------------ unsetting the primary
@pytest.mark.django_db
def test_unsetting_the_current_primary_is_rejected_with_a_clear_error(me, empty_profile):
    first = add(me, 1)
    add(me, 2)

    res = me.patch(f"{URL}{first['id']}/", {"is_primary": False}, format="json")

    assert res.status_code == 400
    error = res.json()["error"]
    assert error["code"] == "validation_error"
    assert error["fields"]["is_primary"] == [
        'You need a primary contact. To change it, choose "Make primary" on another contact.'
    ]
    assert primaries(empty_profile) == [first["id"]]


@pytest.mark.django_db
def test_unsetting_the_only_contact_is_rejected(me, empty_profile):
    only = add(me, 1)
    assert me.patch(f"{URL}{only['id']}/", {"is_primary": False}, format="json").status_code == 400
    assert primaries(empty_profile) == [only["id"]]


@pytest.mark.django_db
def test_rejected_unset_saves_nothing_else_from_the_same_request(me, empty_profile):
    first = add(me, 1)

    res = me.patch(f"{URL}{first['id']}/", {"is_primary": False, "name": "Renamed Person"}, format="json")

    assert res.status_code == 400
    assert EmergencyContact.objects.get(pk=first["id"]).name == "Contact Number1"


@pytest.mark.django_db
def test_editing_the_primary_while_keeping_it_primary_works(me, empty_profile):
    """What the edit form sends for the primary: the whole form, with is_primary still true."""
    first = add(me, 1)

    res = me.patch(f"{URL}{first['id']}/", {"name": "Renamed Person", "relationship": "parent",
                                           "phone": "+92 300 0000001", "is_primary": True}, format="json")

    assert res.status_code == 200
    assert res.data["name"] == "Renamed Person" and res.data["is_primary"] is True
    assert primaries(empty_profile) == [first["id"]]


@pytest.mark.django_db
def test_sending_is_primary_false_for_a_non_primary_contact_is_fine(me, empty_profile):
    """What the edit form sends for a non-primary contact: is_primary false, which changes nothing."""
    first, second = add(me, 1), add(me, 2)

    res = me.patch(f"{URL}{second['id']}/", {"name": "Renamed Person", "is_primary": False}, format="json")

    assert res.status_code == 200
    assert primaries(empty_profile) == [first["id"]]


# ------------------------------------------------------------------ the invariant across a whole session
@pytest.mark.django_db
def test_a_profile_with_contacts_always_has_exactly_one_primary(me, empty_profile):
    """Every way the primary can move, one after another, checking the rule after EVERY step."""
    profile = empty_profile
    assert_invariant(profile)                                            # 0 contacts, 0 primaries

    a = add(me, 1)                                                       # first contact -> primary
    assert_invariant(profile)
    assert primaries(profile) == [a["id"]]

    b = add(me, 2)                                                       # second, not primary
    assert_invariant(profile)
    assert primaries(profile) == [a["id"]]

    c = add(me, 3, is_primary=True)                                      # created as primary -> moves
    assert_invariant(profile)
    assert primaries(profile) == [c["id"]]

    assert me.patch(f"{URL}{b['id']}/", {"is_primary": True}, format="json").status_code == 200  # "Make primary"
    assert_invariant(profile)
    assert primaries(profile) == [b["id"]]

    assert me.patch(f"{URL}{b['id']}/", {"is_primary": False}, format="json").status_code == 400  # unset: refused
    assert_invariant(profile)
    assert primaries(profile) == [b["id"]]

    assert me.patch(f"{URL}{a['id']}/", {"is_primary": False}, format="json").status_code == 200  # non-primary: no-op
    assert_invariant(profile)

    assert me.delete(f"{URL}{b['id']}/").status_code == 204             # delete primary -> oldest promoted
    assert_invariant(profile)
    assert primaries(profile) == [a["id"]]

    assert me.delete(f"{URL}{c['id']}/").status_code == 204             # delete a non-primary
    assert_invariant(profile)
    assert primaries(profile) == [a["id"]]

    assert me.delete(f"{URL}{a['id']}/").status_code == 204             # delete the last one
    assert_invariant(profile)                                            # empty again, no primary

    d = add(me, 4)                                                       # start over: first is primary
    assert_invariant(profile)
    assert primaries(profile) == [d["id"]]


@pytest.mark.django_db
def test_invariant_holds_for_profiles_side_by_side(client, user, other_user):
    """One member's primary changes never affect another member's primary."""
    theirs = make_profile(other_user, sections=("contact",))
    mine = make_profile(user, sections=())
    user_login(client)
    first = add(client, 1)
    add(client, 2, is_primary=True)
    client.patch(f"{URL}{first['id']}/", {"is_primary": True}, format="json")

    assert_invariant(mine)
    assert_invariant(theirs)
    assert len(primaries(theirs)) == 1
