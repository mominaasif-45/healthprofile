"""Phase 2: emergency-contact CRUD, limits, primary rule and member isolation."""
import pytest

from profiles.models import EmergencyContact, HealthProfile

from .conftest import make_profile, user_login

URL = "/api/profiles/me/emergency-contacts/"


def contact(n, **extra):
    return {"name": f"Contact Number{n}", "relationship": "friend", "phone": f"+92 300 000000{n}", **extra}


@pytest.fixture
def me(client, user, empty_profile):
    user_login(client)
    return client


@pytest.mark.django_db
def test_first_contact_becomes_primary_automatically(me):
    res = me.post(URL, contact(1), format="json")
    assert res.status_code == 201 and res.data["is_primary"] is True
    assert me.post(URL, contact(2), format="json").data["is_primary"] is False


@pytest.mark.django_db
def test_making_contact_2_primary_unsets_contact_1(me):
    first = me.post(URL, contact(1), format="json").data
    second = me.post(URL, contact(2), format="json").data
    res = me.patch(f"{URL}{second['id']}/", {"is_primary": True}, format="json")
    assert res.status_code == 200 and res.data["is_primary"] is True
    assert EmergencyContact.objects.get(pk=first["id"]).is_primary is False
    assert EmergencyContact.objects.filter(is_primary=True).count() == 1


@pytest.mark.django_db
def test_creating_with_is_primary_true_moves_the_primary(me):
    first = me.post(URL, contact(1), format="json").data
    second = me.post(URL, contact(2, is_primary=True), format="json").data
    assert second["is_primary"] is True
    assert EmergencyContact.objects.get(pk=first["id"]).is_primary is False


@pytest.mark.django_db
def test_fourth_contact_returns_400(me):
    for n in (1, 2, 3):
        assert me.post(URL, contact(n), format="json").status_code == 201
    res = me.post(URL, contact(4), format="json")
    assert res.status_code == 400
    assert "emergency_contacts" in res.json()["error"]["fields"]
    assert EmergencyContact.objects.count() == 3


@pytest.mark.django_db
def test_duplicate_phone_returns_400(me):
    me.post(URL, contact(1), format="json")
    res = me.post(URL, {**contact(2), "phone": contact(1)["phone"]}, format="json")
    assert res.status_code == 400 and "phone" in res.json()["error"]["fields"]


@pytest.mark.django_db
def test_changing_a_phone_to_an_existing_one_returns_400(me):
    me.post(URL, contact(1), format="json")
    second = me.post(URL, contact(2), format="json").data
    res = me.patch(f"{URL}{second['id']}/", {"phone": contact(1)["phone"]}, format="json")
    assert res.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    "bad, field",
    [
        ({"name": "A", "relationship": "friend", "phone": "+92 300 0000001"}, "name"),
        ({"name": "Contact One", "relationship": "enemy", "phone": "+92 300 0000001"}, "relationship"),
        ({"name": "Contact One", "relationship": "friend", "phone": "call me"}, "phone"),
        ({"name": "Contact One", "relationship": "friend"}, "phone"),
    ],
)
def test_contact_validation_returns_400(me, bad, field):
    res = me.post(URL, bad, format="json")
    assert res.status_code == 400 and field in res.json()["error"]["fields"]


@pytest.mark.django_db
def test_list_get_patch_delete_flow(me):
    created = me.post(URL, contact(1), format="json").data
    assert len(me.get(URL).data) == 1
    assert me.get(f"{URL}{created['id']}/").data["name"] == "Contact Number1"
    patched = me.patch(f"{URL}{created['id']}/", {"relationship": "parent"}, format="json")
    assert patched.data["relationship"] == "parent" and patched.data["name"] == "Contact Number1"
    assert me.delete(f"{URL}{created['id']}/").status_code == 204
    assert me.get(f"{URL}{created['id']}/").status_code == 404


@pytest.mark.django_db
def test_deleting_the_primary_promotes_the_next_contact(me):
    first = me.post(URL, contact(1), format="json").data
    second = me.post(URL, contact(2), format="json").data
    me.delete(f"{URL}{first['id']}/")
    assert EmergencyContact.objects.get(pk=second["id"]).is_primary is True


@pytest.mark.django_db
def test_contacts_move_completion(me, user):
    created = me.post(URL, contact(1), format="json").data
    assert HealthProfile.objects.get(user=user).completion_percent == 25
    me.delete(f"{URL}{created['id']}/")
    assert HealthProfile.objects.get(user=user).completion_percent == 0


# ------------------------------------------------------------------ isolation between members
@pytest.fixture
def two_members(client, user, other_user):
    make_profile(user, sections=("demographics",))
    theirs = make_profile(other_user)
    user_login(client)
    return client, theirs.emergency_contacts.get()


@pytest.mark.django_db
def test_member_cannot_read_edit_or_delete_another_members_contact(two_members):
    client, foreign = two_members
    url = f"{URL}{foreign.id}/"
    assert client.get(url).status_code == 404  # 404, not 403: existence is not revealed
    assert client.patch(url, {"name": "Hacked Name"}, format="json").status_code == 404
    assert client.delete(url).status_code == 404
    foreign.refresh_from_db()
    assert foreign.name == "Sana Ahmed"


@pytest.mark.django_db
def test_listing_never_includes_another_members_contacts(two_members):
    client, foreign = two_members
    assert client.get(URL).data == []
    assert EmergencyContact.objects.filter(pk=foreign.pk).exists()


@pytest.mark.django_db
def test_other_members_phone_is_allowed_on_my_profile(two_members):
    client, foreign = two_members
    res = client.post(URL, {"name": "Same Number", "relationship": "friend", "phone": foreign.phone}, format="json")
    assert res.status_code == 201  # uniqueness is per profile, so nothing about the other member leaks
