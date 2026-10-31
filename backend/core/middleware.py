import uuid


class RequestIdMiddleware:
    """
    Gives every request an id so one user action can be followed through the
    response header, an error body and the audit log.

    An incoming X-Request-ID is trusted ONLY if it is a valid UUID; anything else is
    ignored and a fresh one is generated (so clients cannot inject odd strings into logs).
    Placed first in MIDDLEWARE so it also covers responses made by other middleware
    (for example a CSRF 403).
    """

    header = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(self.header, "")
        try:
            request_id = uuid.UUID(incoming)
        except (ValueError, AttributeError, TypeError):
            request_id = uuid.uuid4()
        request.request_id = request_id

        response = self.get_response(request)
        response[self.header] = str(request_id)
        return response
