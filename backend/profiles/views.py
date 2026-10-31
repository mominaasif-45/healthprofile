"""
Member endpoints. Every route lives under /api/profiles/me/ and is scoped to request.user:
there is no URL that carries another profile's id, so other members' data cannot be reached.
Nested objects (emergency contacts) are looked up ONLY inside the caller's own profile, so a
stranger's contact id returns 404 (not 403), which does not reveal that it exists.

Every write runs the service call AND record_event() in one transaction (write_transaction): if
the required audit event cannot be written, the change and the completion update roll back too.
The service locks the profile row and re-checks that it is still active (see services._lock).
"""
from contextlib import contextmanager

from django.db import transaction
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import CookieJWTAuthentication
from audit.models import AuditEvent
from audit.serializers import MemberActivitySerializer
from audit.services import log_event, record_event

from . import services
from .models import Demographics, EmergencyContact, HealthProfile, WellnessPreference
from .serializers import (
    DemographicsSerializer,
    EmergencyContactSerializer,
    ProfileSerializer,
    WellnessSerializer,
)

Action = AuditEvent.Action
Outcome = AuditEvent.Outcome

TAG = ["member profile"]
COMMON_ERRORS = "401 not signed in, 403 missing CSRF header or profile deactivated, 404 no profile yet."


class ProfileAlreadyExists(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "You already have a profile."
    default_code = "profile_exists"


class MemberView(APIView):
    """Base class: JWT cookie auth + signed-in only, on every member view (declared explicitly)."""

    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_profile(self, request, write_action=None):
        """
        The caller's own profile (404 if none). For writes pass the audit action: a deactivated
        profile is read-only, so the write is refused with 403 and recorded as outcome=denied.
        """
        profile = HealthProfile.objects.filter(user=request.user).first()
        if profile is None:
            raise NotFound("You have not created a profile yet.")
        # Fast path only. The check that counts is repeated on the locked row (write_transaction).
        if write_action and profile.status != HealthProfile.Status.ACTIVE:
            self.deny(request, write_action, profile)
        return profile

    @contextmanager
    def write_transaction(self, request, action, profile):
        """
        One transaction for the service call (which locks the profile row) and its required audit
        event. If the service finds the profile deactivated under the lock, everything rolls back
        FIRST; the denied event is written afterwards, outside that transaction, so it is kept.
        """
        try:
            with transaction.atomic():
                yield
        except services.ProfileDeactivated:
            self.deny(request, action, profile)

    @staticmethod
    def deny(request, action, profile):
        log_event(request, action, target=profile, outcome=Outcome.DENIED)  # best-effort, never raises
        raise PermissionDenied("Your profile is deactivated and can no longer be changed.")


# ---------------------------------------------------------------- root profile
class MyProfileView(MemberView):
    @extend_schema(
        tags=TAG, summary="Get my whole profile",
        description="Returns the root profile with every section (or null / empty list) and the "
                    f"completion status. {COMMON_ERRORS}",
        responses={200: ProfileSerializer},
    )
    def get(self, request):
        return Response(ProfileSerializer(self.get_profile(request)).data)

    @extend_schema(
        tags=TAG, summary="Create my (empty) profile",
        description="Creates the empty root profile. Fill the sections with the routes below. "
                    "409 if you already have one.",
        request=None, responses={201: ProfileSerializer},
    )
    def post(self, request):
        if HealthProfile.objects.filter(user=request.user).exists():
            raise ProfileAlreadyExists()
        with transaction.atomic():
            profile = HealthProfile.objects.create(user=request.user)
            record_event(request, Action.PROFILE_CREATED, target=profile)
        return Response(ProfileSerializer(profile).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=TAG, summary="Delete my profile",
        description="Deletes the profile and ALL its sections. Your account stays, so you can "
                    "sign in and create a new profile. 204 on success.",
        responses={204: None},
    )
    def delete(self, request):
        profile = self.get_profile(request, write_action=Action.PROFILE_DELETED)
        profile_id = profile.pk
        with self.write_transaction(request, Action.PROFILE_DELETED, profile):
            services.delete_profile(profile)  # cascades to demographics, contacts, wellness and goals
            record_event(request, Action.PROFILE_DELETED, target=("health_profile", profile_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- demographics
DEMOGRAPHICS_EXAMPLE = OpenApiExample(
    "Demographics", request_only=True,
    value={"full_name": "Momina Asif", "preferred_name": "Mo", "age_range": "25-34",
           "gender": "female", "city": "Lahore"},
)


class DemographicsView(MemberView):
    def _section(self, profile):
        section = Demographics.objects.filter(profile=profile).first()
        if section is None:
            raise NotFound("Demographics have not been saved yet.")
        return section

    @extend_schema(tags=TAG, summary="Get my demographics", responses={200: DemographicsSerializer})
    def get(self, request):
        return Response(DemographicsSerializer(self._section(self.get_profile(request))).data)

    @extend_schema(
        tags=TAG, summary="Save my demographics (create or replace)",
        description="PUT replaces the whole section: optional fields you leave out are cleared. "
                    "Needs an age range or a date of birth. 201 the first time, 200 afterwards.",
        request=DemographicsSerializer, responses={200: DemographicsSerializer, 201: DemographicsSerializer},
        examples=[DEMOGRAPHICS_EXAMPLE],
    )
    def put(self, request):
        profile = self.get_profile(request, write_action=Action.DEMOGRAPHICS_UPDATED)
        serializer = DemographicsSerializer(data=request.data)  # no instance: PUT is a full replace
        serializer.is_valid(raise_exception=True)
        existed = Demographics.objects.filter(profile=profile).exists()
        with self.write_transaction(request, Action.DEMOGRAPHICS_UPDATED, profile):
            section, changed = services.save_demographics(profile, serializer.validated_data, replace=True)
            record_event(request, Action.DEMOGRAPHICS_UPDATED, target=profile, changed_fields=changed)
        return Response(DemographicsSerializer(section).data,
                        status=status.HTTP_200_OK if existed else status.HTTP_201_CREATED)

    @extend_schema(
        tags=TAG, summary="Change some demographics fields",
        description="PATCH changes only the fields you send. The section must already exist (404 otherwise).",
        request=DemographicsSerializer, responses={200: DemographicsSerializer},
        examples=[OpenApiExample("Change city", request_only=True, value={"city": "Karachi"})],
    )
    def patch(self, request):
        profile = self.get_profile(request, write_action=Action.DEMOGRAPHICS_UPDATED)
        section = self._section(profile)
        serializer = DemographicsSerializer(section, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with self.write_transaction(request, Action.DEMOGRAPHICS_UPDATED, profile):
            section, changed = services.save_demographics(profile, serializer.validated_data, replace=False)
            record_event(request, Action.DEMOGRAPHICS_UPDATED, target=profile, changed_fields=changed)
        return Response(DemographicsSerializer(section).data)


# ---------------------------------------------------------------- wellness
class WellnessView(MemberView):
    def _section(self, profile):
        section = WellnessPreference.objects.filter(profile=profile).first()
        if section is None:
            raise NotFound("Wellness preferences have not been saved yet.")
        return section

    @staticmethod
    def _action(changed):
        # A save that only touched the goals is recorded as goals.updated.
        return Action.GOALS_UPDATED if changed == ["goals"] else Action.WELLNESS_UPDATED

    @extend_schema(tags=TAG, summary="Get my wellness preferences and goals", responses={200: WellnessSerializer})
    def get(self, request):
        return Response(WellnessSerializer(self._section(self.get_profile(request))).data)

    @extend_schema(
        tags=TAG, summary="Save my wellness preferences (create or replace)",
        description="PUT replaces the section. `goals` is a list of goal codes and is replaced "
                    "atomically together with the preferences.",
        request=WellnessSerializer, responses={200: WellnessSerializer, 201: WellnessSerializer},
        examples=[OpenApiExample("Wellness", request_only=True, value={
            "contact_preference": "email", "activity_level": "moderate", "diet_preference": "halal",
            "sleep_goal_hours": 8, "allergies": "Peanuts", "lifestyle_notes": "Prefer morning reminders.",
            "goals": ["better_sleep", "hydration"]})],
    )
    def put(self, request):
        profile = self.get_profile(request, write_action=Action.WELLNESS_UPDATED)
        serializer = WellnessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        existed = WellnessPreference.objects.filter(profile=profile).exists()
        with self.write_transaction(request, Action.WELLNESS_UPDATED, profile):
            section, changed = services.save_wellness(profile, serializer.validated_data, replace=True)
            record_event(request, self._action(changed), target=profile, changed_fields=changed)
        return Response(WellnessSerializer(section).data,
                        status=status.HTTP_200_OK if existed else status.HTTP_201_CREATED)

    @extend_schema(
        tags=TAG, summary="Change some wellness fields",
        description="PATCH changes only the fields you send (goals, if sent, replace the saved goals).",
        request=WellnessSerializer, responses={200: WellnessSerializer},
        examples=[OpenApiExample("Change goals", request_only=True, value={"goals": ["better_sleep"]})],
    )
    def patch(self, request):
        profile = self.get_profile(request, write_action=Action.WELLNESS_UPDATED)
        section = self._section(profile)
        serializer = WellnessSerializer(section, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with self.write_transaction(request, Action.WELLNESS_UPDATED, profile):
            section, changed = services.save_wellness(profile, serializer.validated_data, replace=False)
            record_event(request, self._action(changed), target=profile, changed_fields=changed)
        return Response(WellnessSerializer(section).data)


# ---------------------------------------------------------------- emergency contacts
CONTACT_EXAMPLE = OpenApiExample(
    "Contact", request_only=True,
    value={"name": "Bilal Ahmed", "relationship": "sibling", "phone": "+92 300 0000000", "is_primary": True},
)


class ContactListView(MemberView):
    @extend_schema(tags=TAG, summary="List my emergency contacts (max 3)",
                   responses={200: EmergencyContactSerializer(many=True)})
    def get(self, request):
        profile = self.get_profile(request)
        return Response(EmergencyContactSerializer(profile.emergency_contacts.all(), many=True).data)

    @extend_schema(
        tags=TAG, summary="Add an emergency contact",
        description="Maximum 3 per profile (a 4th returns 400). The first contact becomes primary "
                    "automatically; sending is_primary=true un-sets the previous primary.",
        request=EmergencyContactSerializer, responses={201: EmergencyContactSerializer},
        examples=[CONTACT_EXAMPLE],
    )
    def post(self, request):
        profile = self.get_profile(request, write_action=Action.CONTACT_CREATED)
        serializer = EmergencyContactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with self.write_transaction(request, Action.CONTACT_CREATED, profile):
            contact = services.create_contact(profile, serializer.validated_data)
            record_event(request, Action.CONTACT_CREATED, target=profile,
                         changed_fields=sorted(serializer.validated_data))
        return Response(EmergencyContactSerializer(contact).data, status=status.HTTP_201_CREATED)


class ContactDetailView(MemberView):
    def _contact(self, profile, pk):
        # Looked up inside the caller's own profile only: someone else's id is simply "not found".
        contact = EmergencyContact.objects.filter(profile=profile, pk=pk).first()
        if contact is None:
            raise NotFound("Emergency contact not found.")
        return contact

    @extend_schema(tags=TAG, summary="Get one of my emergency contacts", responses={200: EmergencyContactSerializer})
    def get(self, request, pk):
        return Response(EmergencyContactSerializer(self._contact(self.get_profile(request), pk)).data)

    @extend_schema(
        tags=TAG, summary="Change an emergency contact",
        description="Send only the fields to change. A profile with contacts always has exactly one "
                    "primary: is_primary=true moves the primary here, and is_primary=false on the current "
                    "primary returns 400 (choose another contact as primary instead).",
        request=EmergencyContactSerializer, responses={200: EmergencyContactSerializer},
        examples=[OpenApiExample("Make primary", request_only=True, value={"is_primary": True})],
    )
    def patch(self, request, pk):
        profile = self.get_profile(request, write_action=Action.CONTACT_UPDATED)
        contact = self._contact(profile, pk)
        serializer = EmergencyContactSerializer(contact, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with self.write_transaction(request, Action.CONTACT_UPDATED, profile):
            contact, changed = services.update_contact(contact, serializer.validated_data)
            record_event(request, Action.CONTACT_UPDATED, target=profile, changed_fields=changed)
        return Response(EmergencyContactSerializer(contact).data)

    @extend_schema(tags=TAG, summary="Delete an emergency contact",
                   description="If you delete the primary contact, the oldest remaining contact becomes primary.",
                   responses={204: None})
    def delete(self, request, pk):
        profile = self.get_profile(request, write_action=Action.CONTACT_DELETED)
        contact = self._contact(profile, pk)
        with self.write_transaction(request, Action.CONTACT_DELETED, profile):
            services.delete_contact(contact)
            record_event(request, Action.CONTACT_DELETED, target=profile)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- activity
class MyActivityView(ListAPIView):
    """The member's own audit trail, newest first (served by index audit_actor_created_idx)."""

    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = MemberActivitySerializer

    def get_queryset(self):
        return AuditEvent.objects.filter(actor=self.request.user).order_by("-created_at", "-id")

    @extend_schema(tags=TAG, summary="My activity history",
                   description="Paginated list of my own profile changes (field names only, never values).")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
