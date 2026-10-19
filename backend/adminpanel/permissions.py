from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """
    Allows only logged-in users whose role is 'admin' in the DATABASE.
    request.user is loaded from the server-side session row, never from
    anything the browser sends about itself.
    """

    message = "Admin access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.role == "admin")
