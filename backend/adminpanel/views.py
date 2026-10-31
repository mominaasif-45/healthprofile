from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.authentication import enforce_csrf
from accounts.models import User
from accounts.serializers import LoginSerializer, UserSerializer
from accounts.views import InvalidCredentials
from audit.models import AuditEvent
from audit.serializers import AdminAuditEventSerializer
from audit.services import log_event, record_event
from profiles.models import HealthProfile

from .permissions import IsAdminRole
from .serializers import (
    AdminProfileDetailSerializer,
    AdminProfileListSerializer,
    AdminProfileQuerySerializer,
    AuditEventQuerySerializer,
)

Action = AuditEvent.Action
Outcome = AuditEvent.Outcome

# Every admin view accepts ONLY a server-side session. A user's JWT cookie is
# never looked at here, so it returns 403 on every admin route.
ADMIN_AUTH = [SessionAuthentication]
ADMIN_PERMISSIONS = [IsAuthenticated, IsAdminRole]

TAG_AUTH = ["admin auth"]
TAG_PROFILES = ["admin profiles"]
TAG_AUDIT = ["admin audit"]
SESSION_NOTE = "Requires an admin session (sessionid cookie). Members' JWTs get 403."
CSRF_NOTE = " Send the X-CSRFToken header (403 without it)."


def _date_params():
    return [
        OpenApiParameter("created_after", str, description="YYYY-MM-DD, inclusive"),
        OpenApiParameter("created_before", str, description="YYYY-MM-DD, inclusive"),
    ]


# ------------------------------------------------------------------ session auth
class AdminLoginView(APIView):
    """Admins sign in here. Creates a server-side session (sessionid cookie)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"  # 5 attempts per minute, same limit as member login

    @extend_schema(
        tags=TAG_AUTH, summary="Admin sign in",
        description="Starts a server-side session (30 minutes idle). Admins are created only with "
                    "`manage.py create_admin`. A member's credentials get 403. Throttled to 5 per minute (429)."
                    + CSRF_NOTE,
        request=LoginSerializer, responses={200: UserSerializer},
        examples=[OpenApiExample("Login", request_only=True,
                                 value={"email": "admin@healthprofile.test", "password": "••••••••••"})],
    )
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
            # No email is stored: the attempted address could be someone's real one.
            log_event(request, Action.ADMIN_LOGIN_FAILED, outcome=Outcome.FAILED)
            raise InvalidCredentials()
        if user.role != User.Role.ADMIN:
            log_event(request, Action.ADMIN_LOGIN_FAILED, outcome=Outcome.DENIED, actor=user)
            raise PermissionDenied("This portal is for administrators only.")

        login(request, user)  # creates the session row and sets the sessionid cookie
        log_event(request, Action.ADMIN_LOGIN, actor=user)
        return Response(UserSerializer(user).data)


class AdminLogoutView(APIView):
    """Deletes the session row on the server, so the old cookie is useless."""

    authentication_classes = ADMIN_AUTH
    permission_classes = ADMIN_PERMISSIONS

    @extend_schema(tags=TAG_AUTH, summary="Admin sign out",
                   description="Deletes the session on the server. " + SESSION_NOTE + CSRF_NOTE,
                   request=None, responses={204: None})
    def post(self, request):
        log_event(request, Action.ADMIN_LOGOUT)  # before logout(), while the actor is still known
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminMeView(APIView):
    authentication_classes = ADMIN_AUTH
    permission_classes = ADMIN_PERMISSIONS

    @extend_schema(tags=TAG_AUTH, summary="Who am I (admin)", description=SESSION_NOTE,
                   responses={200: UserSerializer})
    def get(self, request):
        return Response(UserSerializer(request.user).data)


# ------------------------------------------------------------------ profiles
def _with_sections(qs):
    return qs.select_related("user", "demographics", "wellness").prefetch_related(
        "emergency_contacts", "wellness__goals"
    )


class AdminProfileListView(ListAPIView):
    """Paginated list with search, filters and ordering. Returns only the allow-listed fields."""

    authentication_classes = ADMIN_AUTH
    permission_classes = ADMIN_PERMISSIONS
    serializer_class = AdminProfileListSerializer

    def get_queryset(self):
        params = AdminProfileQuerySerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)  # bad values -> 400 with field errors
        p = params.validated_data

        qs = HealthProfile.objects.select_related("user", "demographics")
        if "status" in p:
            qs = qs.filter(status=p["status"])
        if "completion_status" in p:
            qs = qs.filter(completion_status=p["completion_status"])
        if "created_after" in p:
            qs = qs.filter(created_at__date__gte=p["created_after"])
        if "created_before" in p:
            qs = qs.filter(created_at__date__lte=p["created_before"])
        if p.get("search", "").strip():
            term = p["search"].strip()
            qs = qs.filter(
                Q(demographics__full_name__icontains=term)
                | Q(demographics__preferred_name__icontains=term)
                | Q(user__name__icontains=term)
                | Q(user__email__icontains=term)
            )
        ordering = p.get("ordering", "-created_at")
        # id breaks ties so pages are stable. With ?status= the default order uses
        # profile_status_created_idx (status, created_at DESC).
        return qs.order_by(ordering, "-id" if ordering.startswith("-") else "id")

    @extend_schema(
        tags=TAG_PROFILES, summary="List and search member profiles",
        description="Filters combine with AND. Invalid values return 400 with field errors. "
                    "Paginated (10 per page). " + SESSION_NOTE,
        parameters=[
            OpenApiParameter("search", str, description="Name or email contains (case-insensitive)"),
            OpenApiParameter("status", str, enum=["active", "deactivated"]),
            OpenApiParameter("completion_status", str, enum=["not_started", "in_progress", "complete"]),
            OpenApiParameter("ordering", str,
                             enum=["created_at", "-created_at", "completion_percent", "-completion_percent"]),
            OpenApiParameter("page", int),
            *_date_params(),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AdminProfileDetailView(APIView):
    authentication_classes = ADMIN_AUTH
    permission_classes = ADMIN_PERMISSIONS

    @extend_schema(
        tags=TAG_PROFILES, summary="One profile (sensitive fields hidden)",
        description="Date of birth, allergies and lifestyle notes are never returned; emergency-contact "
                    "phones are masked. Every view is recorded as an audit event. " + SESSION_NOTE,
        responses={200: AdminProfileDetailSerializer},
    )
    def get(self, request, pk):
        profile = get_object_or_404(_with_sections(HealthProfile.objects.all()), pk=pk)
        log_event(request, Action.ADMIN_PROFILE_VIEWED, target=profile)
        return Response(AdminProfileDetailSerializer(profile).data)


class _StatusChangeView(APIView):
    """Shared by deactivate / reactivate. State-changing, so SessionAuthentication enforces CSRF."""

    authentication_classes = ADMIN_AUTH
    permission_classes = ADMIN_PERMISSIONS
    new_status = None
    action = None

    def post(self, request, pk):
        profile = get_object_or_404(_with_sections(HealthProfile.objects.all()), pk=pk)
        changed = profile.status != self.new_status
        with transaction.atomic():  # the status change and its required audit event commit together
            if changed:
                profile.status = self.new_status
                profile.save(update_fields=["status", "updated_at"])
            record_event(request, self.action, target=profile, changed_fields=["status"] if changed else [])
        return Response(AdminProfileDetailSerializer(profile).data)


class AdminProfileDeactivateView(_StatusChangeView):
    new_status = HealthProfile.Status.DEACTIVATED
    action = Action.ADMIN_PROFILE_DEACTIVATED

    @extend_schema(tags=TAG_PROFILES, summary="Deactivate a profile",
                   description="The owner can still read the profile but can no longer change it. "
                                + SESSION_NOTE + CSRF_NOTE,
                   request=None, responses={200: AdminProfileDetailSerializer})
    def post(self, request, pk):
        return super().post(request, pk)


class AdminProfileReactivateView(_StatusChangeView):
    new_status = HealthProfile.Status.ACTIVE
    action = Action.ADMIN_PROFILE_REACTIVATED

    @extend_schema(tags=TAG_PROFILES, summary="Reactivate a profile",
                   description="Lets the owner edit the profile again. " + SESSION_NOTE + CSRF_NOTE,
                   request=None, responses={200: AdminProfileDetailSerializer})
    def post(self, request, pk):
        return super().post(request, pk)


# ------------------------------------------------------------------ audit trail (read-only)
class AdminProfileAuditView(ListAPIView):
    """History of ONE profile (served by audit_target_created_idx)."""

    authentication_classes = ADMIN_AUTH
    permission_classes = ADMIN_PERMISSIONS
    serializer_class = AdminAuditEventSerializer

    def get_queryset(self):
        profile = get_object_or_404(HealthProfile, pk=self.kwargs["pk"])
        return AuditEvent.objects.filter(target_type="health_profile", target_id=profile.pk).order_by(
            "-created_at", "-id"
        )

    @extend_schema(tags=TAG_AUDIT, summary="History of one profile",
                   description="Newest first, paginated. Field names only, never values. " + SESSION_NOTE)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AdminAuditEventListView(ListAPIView):
    """All audit events, read-only. There is no create, update or delete route."""

    authentication_classes = ADMIN_AUTH
    permission_classes = ADMIN_PERMISSIONS
    serializer_class = AdminAuditEventSerializer

    def get_queryset(self):
        params = AuditEventQuerySerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        p = params.validated_data

        qs = AuditEvent.objects.all()
        if "action" in p:
            qs = qs.filter(action=p["action"])
        if "actor" in p:
            qs = qs.filter(actor_id=p["actor"])  # served by audit_actor_created_idx
        if "outcome" in p:
            qs = qs.filter(outcome=p["outcome"])
        if "created_after" in p:
            qs = qs.filter(created_at__date__gte=p["created_after"])
        if "created_before" in p:
            qs = qs.filter(created_at__date__lte=p["created_before"])
        return qs.order_by("-created_at", "-id")

    @extend_schema(
        tags=TAG_AUDIT, summary="All audit events",
        description="Read-only, newest first, paginated. " + SESSION_NOTE,
        parameters=[
            OpenApiParameter("action", str), OpenApiParameter("actor", int, description="User id"),
            OpenApiParameter("outcome", str, enum=["success", "denied", "failed"]),
            OpenApiParameter("page", int), *_date_params(),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
