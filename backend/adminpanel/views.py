from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.authentication import enforce_csrf
from accounts.models import User
from accounts.serializers import LoginSerializer, UserSerializer
from accounts.views import InvalidCredentials
from profiles.models import HealthProfile

from .permissions import IsAdminRole
from .serializers import AdminProfileDetailSerializer, AdminProfileListSerializer

# Every admin view accepts ONLY a server-side session. A user's JWT cookie is
# never looked at here, so it returns 403 on every admin route.
ADMIN_AUTH = [SessionAuthentication]
ADMIN_PERMISSIONS = [IsAuthenticated, IsAdminRole]


class AdminLoginView(APIView):
    """Admins sign in here. Creates a server-side session (sessionid cookie)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses={200: UserSerializer}, tags=["admin"])
    def post(self, request):
        enforce_csrf(request)  # login CSRF: prevents forced logins from other sites
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            raise InvalidCredentials()
        if user.role != User.Role.ADMIN:
            raise PermissionDenied("This portal is for administrators only.")

        login(request, user)  # creates the session row and sets the sessionid cookie
        return Response(UserSerializer(user).data)


class AdminLogoutView(APIView):
    """Deletes the session row on the server, so the old cookie is useless."""

    authentication_classes = ADMIN_AUTH
    permission_classes = ADMIN_PERMISSIONS

    @extend_schema(request=None, responses={204: None}, tags=["admin"])
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminMeView(APIView):
    authentication_classes = ADMIN_AUTH
    permission_classes = ADMIN_PERMISSIONS

    @extend_schema(responses={200: UserSerializer}, tags=["admin"])
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class AdminProfileListView(ListAPIView):
    """Paginated list with search (name or email) and a status filter."""

    authentication_classes = ADMIN_AUTH
    permission_classes = ADMIN_PERMISSIONS
    serializer_class = AdminProfileListSerializer

    def get_queryset(self):
        qs = HealthProfile.objects.select_related("user")

        status_param = self.request.query_params.get("status", "").strip().lower()
        if status_param:
            if status_param not in HealthProfile.Status.values:
                raise ValidationError({"status": ["Use 'active' or 'deactivated'."]})
            qs = qs.filter(status=status_param)

        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(full_name__icontains=search) | Q(user__email__icontains=search))

        return qs.order_by("-created_at", "-id")  # (status, created_at DESC) index is used when ?status= is filtered

    @extend_schema(
        tags=["admin"],
        parameters=[
            OpenApiParameter("search", str, description="Name or email contains"),
            OpenApiParameter("status", str, enum=["active", "deactivated"]),
            OpenApiParameter("page", int),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AdminProfileDetailView(RetrieveAPIView):
    authentication_classes = ADMIN_AUTH
    permission_classes = ADMIN_PERMISSIONS
    serializer_class = AdminProfileDetailSerializer
    queryset = HealthProfile.objects.select_related("user")


class AdminProfileDeactivateView(APIView):
    """State-changing, so SessionAuthentication enforces the X-CSRFToken header."""

    authentication_classes = ADMIN_AUTH
    permission_classes = ADMIN_PERMISSIONS

    @extend_schema(request=None, responses={200: AdminProfileDetailSerializer}, tags=["admin"])
    def post(self, request, pk):
        profile = get_object_or_404(HealthProfile.objects.select_related("user"), pk=pk)
        profile.status = HealthProfile.Status.DEACTIVATED
        profile.save(update_fields=["status", "updated_at"])
        return Response(AdminProfileDetailSerializer(profile).data)
