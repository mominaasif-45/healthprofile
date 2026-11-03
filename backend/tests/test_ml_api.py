"""
Week 3, phase 5: POST /api/ml/v1/no-show/predict/, the versioned prediction endpoint.

Member-only (JWT cookie + CSRF), throttled, validated against the loaded model's own metadata schema,
never stores or logs inputs, and answers 503 model_unavailable if the checksum-verified model cannot load.
"""
import json
import logging

import pytest
from drf_spectacular.generators import SchemaGenerator

from audit.models import AuditEvent
from ml import artifact, features

from .conftest import PASSWORD, admin_login, csrf_header, make_profile, user_login

URL = "/api/ml/v1/no-show/predict/"
VALID = {
    "lead_time_days": 21, "weekday": "mon", "hour": 9, "visit_type": "new_visit",
    "booking_channel": "online", "reminder_sent": "no", "prior_visits": 3,
    "prior_no_shows": 1, "distance_band": "15_30km", "age_band": None,
}
BLANKABLE = ["reminder_sent", "prior_visits", "prior_no_shows", "distance_band", "age_band"]
REQUIRED_NOT_BLANK = ["lead_time_days", "weekday", "hour", "visit_type", "booking_channel"]


def _reset_model_cache():
    try:
        from ml import predictor
    except ImportError:  # only before phase 5 existed: lets these tests fail with 404, not stop at import
        return
    predictor.reset()


@pytest.fixture(autouse=True)
def _fresh_model_cache():
    """Every test starts and ends with no model loaded, so loading behaviour is tested from scratch."""
    _reset_model_cache()
    yield
    _reset_model_cache()


@pytest.fixture
def member(client, user):
    assert user_login(client).status_code == 200
    return client


def body(**changes):
    return {**VALID, **changes}


def post(client, data):
    return client.post(URL, data, format="json")


def assert_error(res, status, code):
    assert res.status_code == status, res.content
    error = res.json()["error"]
    assert error["code"] == code
    assert set(error) >= {"code", "message", "fields", "request_id"}
    return error


# ---------------------------------------------------------------- who may call it
def test_signed_out_is_401(client, db):
    assert_error(post(client, VALID), 401, "not_authenticated")


def test_admin_session_is_401_like_every_member_route(client, admin):
    assert admin_login(client).status_code == 200
    assert post(client, VALID).status_code == 401


def _csrf_member(csrf_client, user):
    """A client that enforces CSRF like a browser, signed in as the member; returns the CSRF header."""
    headers = csrf_header(csrf_client)
    login = {"email": user.email, "password": PASSWORD}
    assert csrf_client.post("/api/auth/user/login/", login, format="json", **headers).status_code == 200
    return headers


def test_member_without_csrf_header_is_403(csrf_client, user):
    _csrf_member(csrf_client, user)
    res = csrf_client.post(URL, VALID, format="json")  # no X-CSRFToken header
    assert res.status_code == 403 and "CSRF" in res.json()["error"]["message"]


def test_member_with_csrf_header_gets_a_prediction(csrf_client, user):
    headers = _csrf_member(csrf_client, user)
    assert csrf_client.post(URL, VALID, format="json", **headers).status_code == 200


def test_get_is_not_allowed(member):
    assert_error(member.get(URL), 405, "method_not_allowed")


def test_member_without_a_profile_may_use_the_demo(member):
    assert post(member, VALID).status_code == 200


def test_member_with_a_deactivated_profile_may_use_the_demo(member, user):
    make_profile(user, status="deactivated")
    assert post(member, VALID).status_code == 200


# ---------------------------------------------------------------- a successful prediction
def test_valid_request_returns_prediction_probability_and_version(member):
    res = post(member, VALID)
    assert res.status_code == 200
    data = res.json()
    assert set(data) == {"prediction", "probability", "threshold", "model_version", "disclaimer"}
    assert data["prediction"] in ("likely_no_show", "likely_attend")
    assert 0 < data["probability"] < 1
    assert data["model_version"] == "noshow-1.0.0"
    assert data["threshold"] == 0.22
    assert "not medical advice" in data["disclaimer"].lower()


def test_probability_and_label_come_from_the_model_itself(member):
    import pandas as pd

    pipeline, metadata = artifact.load_verified()
    expected = float(pipeline.predict_proba(pd.DataFrame([VALID])[features.FEATURES])[:, 1][0])
    data = post(member, VALID).json()
    assert data["probability"] == round(expected, 4)
    assert data["prediction"] == ("likely_no_show" if expected >= metadata["threshold"] else "likely_attend")


def test_blank_is_accepted_where_the_schema_allows_it(member):
    assert post(member, body(**{name: None for name in BLANKABLE})).status_code == 200


# ---------------------------------------------------------------- rejected input
@pytest.mark.parametrize("name", list(VALID))
def test_every_field_is_required(member, name):
    data = dict(VALID)
    del data[name]
    error = assert_error(post(member, data), 400, "validation_error")
    assert name in error["fields"]


@pytest.mark.parametrize("name", REQUIRED_NOT_BLANK)
def test_blank_is_rejected_where_the_schema_forbids_it(member, name):
    error = assert_error(post(member, body(**{name: None})), 400, "validation_error")
    assert name in error["fields"]


@pytest.mark.parametrize(
    "name, value",
    [
        ("lead_time_days", -1), ("lead_time_days", 91), ("hour", 7), ("hour", 18),
        ("prior_visits", -1), ("prior_visits", 21), ("prior_no_shows", -1),
    ],
)
def test_out_of_range_numbers_are_rejected(member, name, value):
    error = assert_error(post(member, body(**{name: value})), 400, "validation_error")
    assert name in error["fields"]


@pytest.mark.parametrize(
    "name, value",
    [
        ("lead_time_days", "21"), ("lead_time_days", 21.5), ("lead_time_days", 21.0), ("lead_time_days", True),
        ("lead_time_days", {}), ("hour", [9]), ("weekday", 1), ("weekday", "Monday"), ("weekday", "sun"),
        ("weekday", ""), ("reminder_sent", "maybe"), ("reminder_sent", True), ("age_band", "70+"),
    ],
)
def test_wrong_types_and_unknown_values_are_rejected(member, name, value):
    error = assert_error(post(member, body(**{name: value})), 400, "validation_error")
    assert name in error["fields"]


@pytest.mark.parametrize(
    "changes",
    [{"prior_visits": 2, "prior_no_shows": 4}, {"prior_visits": None, "prior_no_shows": 1},
     {"prior_visits": 3, "prior_no_shows": None}],
)
def test_prior_visit_rules_are_enforced(member, changes):
    error = assert_error(post(member, body(**changes)), 400, "validation_error")
    assert "prior_no_shows" in error["fields"]


@pytest.mark.parametrize("extra", ["no_show", "role", "full_name", "appointment_id"])
def test_extra_fields_are_rejected_not_ignored(member, extra):
    error = assert_error(post(member, body(**{extra: 1})), 400, "validation_error")
    assert error["fields"][extra] == ["Unknown field."]


@pytest.mark.parametrize("payload", [[VALID], "lead_time_days=21", 42])
def test_a_body_that_is_not_an_object_is_rejected(member, payload):
    assert_error(post(member, payload), 400, "validation_error")


def test_broken_json_is_rejected(member):
    res = member.post(URL, data='{"lead_time_days": 21,', content_type="application/json")
    assert_error(res, 400, "parse_error")


# ---------------------------------------------------------------- nothing echoed, logged or stored
def test_error_messages_never_repeat_the_submitted_value(member):
    res = post(member, body(weekday="SECRET-7", visit_type="SECRET-8", lead_time_days="SECRET-9"))
    assert res.status_code == 400
    assert "SECRET" not in res.content.decode()


def test_nothing_is_logged_or_stored(member, caplog):
    before = AuditEvent.objects.count()
    with caplog.at_level(logging.DEBUG):
        assert post(member, body(lead_time_days=73, distance_band="over_30km")).status_code == 200
        assert post(member, body(weekday="SECRET-7")).status_code == 400
    logged = " ".join(record.getMessage() for record in caplog.records)
    for value in ("73", "over_30km", "SECRET-7", "likely_", "probability"):
        assert value not in logged
    assert AuditEvent.objects.count() == before


# ---------------------------------------------------------------- loading the model
def test_model_is_loaded_once_and_reused(member, monkeypatch):
    calls = []
    real = artifact.load_verified

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(artifact, "load_verified", counting)
    assert post(member, VALID).status_code == 200
    assert post(member, body(hour=15)).status_code == 200
    assert len(calls) == 1


@pytest.mark.parametrize(
    "failure", [artifact.ArtifactUnavailable, artifact.ArtifactIntegrityError, artifact.ArtifactIncompatible]
)
def test_a_model_that_cannot_load_gives_503_and_logs_only_the_error_type(member, monkeypatch, caplog, failure):
    def broken(*args, **kwargs):
        raise failure("detail that must not be logged")

    monkeypatch.setattr(artifact, "load_verified", broken)
    with caplog.at_level(logging.WARNING):
        error = assert_error(post(member, VALID), 503, "model_unavailable")
    assert error["fields"] == {}
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert failure.__name__ in logged and "detail that must not be logged" not in logged


def test_a_failed_load_is_not_cached(member, monkeypatch):
    real = artifact.load_verified

    def broken(*args, **kwargs):
        raise artifact.ArtifactUnavailable("missing")

    monkeypatch.setattr(artifact, "load_verified", broken)
    assert post(member, VALID).status_code == 503
    monkeypatch.setattr(artifact, "load_verified", real)  # the file is "fixed"
    assert post(member, VALID).status_code == 200


def test_a_tampered_model_file_gives_503(member, monkeypatch, tmp_path):
    tampered = tmp_path / artifact.MODEL_PATH.name
    data = bytearray(artifact.MODEL_PATH.read_bytes())
    data[100] ^= 0xFF
    tampered.write_bytes(bytes(data))
    monkeypatch.setattr(artifact, "MODEL_PATH", tampered)
    assert_error(post(member, VALID), 503, "model_unavailable")


# ---------------------------------------------------------------- throttle
def test_31st_request_in_a_minute_is_throttled(member):
    for _ in range(30):
        assert post(member, VALID).status_code == 200
    assert_error(post(member, VALID), 429, "throttled")


# ---------------------------------------------------------------- Swagger
def test_swagger_documents_the_endpoint_from_the_metadata_schema():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    operation = schema["paths"][URL]["post"]
    assert operation["tags"] == ["ml demo (educational)"]
    assert "not medical advice" in operation["description"].lower()
    for status in ("200", "400", "401", "403", "429", "503"):
        assert status in operation["responses"]
    ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
    documented = schema["components"]["schemas"][ref]
    assert list(documented["properties"]) == features.FEATURES
    assert set(documented["required"]) == set(features.FEATURES)


def test_documented_fields_equal_the_runtime_fields(member):
    from ml import predictor
    from ml.serializers import NoShowRequestDocs

    post(member, VALID)  # loads the model
    runtime = predictor.get_predictor().serializer_class().fields
    docs = NoShowRequestDocs().fields
    assert list(runtime) == list(docs) == features.FEATURES
    for name in features.FEATURES:
        assert type(runtime[name]) is type(docs[name])
        assert runtime[name].allow_null == docs[name].allow_null
        assert getattr(runtime[name], "choices", None) == getattr(docs[name], "choices", None)
        assert getattr(runtime[name], "min_value", None) == getattr(docs[name], "min_value", None)
        assert getattr(runtime[name], "max_value", None) == getattr(docs[name], "max_value", None)


def test_the_examples_in_the_docs_are_real_requests_and_real_responses(member):
    """Each documented request, sent for real, returns exactly the documented response."""
    from ml.views import EXAMPLES

    assert {response["prediction"] for _, response in EXAMPLES} == {"likely_no_show", "likely_attend"}
    for request_body, response in EXAMPLES:
        res = post(member, json.loads(json.dumps(request_body)))
        assert res.status_code == 200
        assert res.json() == response
