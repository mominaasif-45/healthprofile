"""
Two ways to write an audit event:

  record_event()  REQUIRED. For every successful data change (member writes, admin
                  deactivate / reactivate). Must run inside the same transaction.atomic()
                  as the change. If the insert fails it raises AuditUnavailable (503), so
                  the change rolls back with it: no change is ever committed without its event.

  log_event()     BEST-EFFORT. For logins, logouts, admin views and denied writes, where
                  nothing was changed. A failed insert only logs a warning.
"""
import logging
import re

from django.db import DatabaseError, transaction
from rest_framework import status
from rest_framework.exceptions import APIException

from .models import AuditEvent

logger = logging.getLogger(__name__)

# Only plain snake_case names may be recorded as "changed fields". A value such as a phone
# number, an email or a sentence can never match, so a developer cannot log one by mistake.
FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MAX_FIELDS = 20


class AuditUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Your change was not saved because it could not be recorded. Please try again."
    default_code = "audit_unavailable"


def record_event(request, action, target=None, changed_fields=None, outcome="success", actor=None):
    """
    Write ONE required audit event inside the caller's transaction. Raises AuditUnavailable
    if it cannot be written, which rolls back the whole transaction (the change included).
    Same arguments as log_event().
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("record_event() must be called inside transaction.atomic() with the change it records.")
    try:
        _create(request, action, target, changed_fields, outcome, actor)
    except DatabaseError as exc:
        # The exception class name only: never the message, which could quote a value.
        logger.error("Required audit event %s failed (%s); rolling back", action, type(exc).__name__)
        raise AuditUnavailable() from exc


def log_event(request, action, target=None, changed_fields=None, outcome="success", actor=None):
    """
    Write ONE best-effort audit event. Safe to call from any view:
      - it never raises into the request (a failed audit write only logs a warning),
      - it accepts only field NAMES, never values,
      - the actor and request id come from the request itself.

    target: a model instance (usually the HealthProfile), a (type, id) tuple, or None.
    actor:  pass explicitly when request.user is not set yet (e.g. right after login).
    """
    try:
        # Savepoint: if the insert fails inside a caller's transaction, only the savepoint is
        # rolled back. Without it, PostgreSQL would refuse every later query in that transaction.
        with transaction.atomic():
            _create(request, action, target, changed_fields, outcome, actor)
    except Exception:  # noqa: BLE001 - auditing must never break the request
        logger.warning("Could not write audit event %s", action, exc_info=True)


def _create(request, action, target, changed_fields, outcome, actor):
    user = actor if actor is not None else getattr(request, "user", None)
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None

    target_type, target_id = "", None
    if isinstance(target, tuple):
        target_type, target_id = target
    elif target is not None:
        target_type, target_id = _target_type(target), target.pk

    names = []
    for name in changed_fields or []:
        if isinstance(name, str) and FIELD_NAME.match(name) and name not in names:
            names.append(name)

    AuditEvent.objects.create(
        actor=user,
        actor_role=getattr(user, "role", None) or "anonymous",
        action=action,
        target_type=target_type,
        target_id=target_id,
        changed_fields=names[:MAX_FIELDS],
        request_id=getattr(request, "request_id", None),
        outcome=outcome,
    )


def _target_type(obj):
    return {"HealthProfile": "health_profile"}.get(type(obj).__name__, type(obj).__name__.lower())
