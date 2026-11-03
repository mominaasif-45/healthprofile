from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """
    Turn every DRF error into ONE consistent shape:
    {"error": {"code": "...", "message": "...", "fields": {...}}}
    """
    response = exception_handler(exc, context)
    if response is None:
        return None  # unexpected server error: Django returns a plain 500

    data = response.data

    if isinstance(data, dict) and set(data.keys()) == {"detail"}:
        # Errors like 401 Not authenticated, 403 Forbidden, 404 Not found, 429 Throttled
        detail = data["detail"]
        code = getattr(detail, "code", "error")
        message = str(detail)
        fields = {}
    else:
        # Validation errors: one message per field, e.g. {"email": ["..."]}
        code = "validation_error"
        message = "Invalid input."
        fields = data if isinstance(data, dict) else {"non_field_errors": data}

    error = {"code": code, "message": message, "fields": fields}
    request_id = getattr(context.get("request"), "request_id", None)
    if request_id is not None:
        error["request_id"] = str(request_id)  # lets a user quote it when reporting a problem
    response.data = {"error": error}
    return response