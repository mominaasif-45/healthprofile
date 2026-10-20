import logging
import re

from .models import AuditEvent

logger = logging.getLogger(__name__)

# Only plain snake_case names may be recorded as "changed fields". A value such as a phone
# number, an email or a sentence can never match, so a developer cannot log one by mistake.
FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MAX_FIELDS = 20


def log_event(request, action, target=None, changed_fields=None, outcome="success", actor=None):
    """
    Write ONE audit event. Safe to call from any view:
      - it never raises into the request (a failed audit write only logs a warning),
      - it accepts only field NAMES, never values,
      - the actor and request id come from the request itself.

    target: a model instance (usually the HealthProfile), a (type, id) tuple, or None.
    actor:  pass explicitly when request.user is not set yet (e.g. right after login).
    """
    try:
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
    except Exception:  # noqa: BLE001 - auditing must never break the request
        logger.warning("Could not write audit event %s", action, exc_info=True)


def _target_type(obj):
    return {"HealthProfile": "health_profile"}.get(type(obj).__name__, type(obj).__name__.lower())
