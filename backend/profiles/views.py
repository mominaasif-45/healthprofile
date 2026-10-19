from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import CookieJWTAuthentication

from .models import HealthProfile
from .serializers import ProfileSerializer


class ProfileAlreadyExists(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "You already have a profile. Use PATCH to update it."
    default_code = "profile_exists"


class MyProfileView(APIView):
    """
    The only profile route for standard users. There is deliberately no
    /profiles/{id}/ route, so reading someone else's profile is impossible
    (no IDOR). The profile is always looked up from request.user.
    """

    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_profile(self, request):
        profile = HealthProfile.objects.filter(user=request.user).first()
        if profile is None:
            raise NotFound("You have not created a profile yet.")
        return profile

    @extend_schema(responses={200: ProfileSerializer}, tags=["profile"])
    def get(self, request):
        return Response(ProfileSerializer(self._get_profile(request)).data)

    @extend_schema(request=ProfileSerializer, responses={201: ProfileSerializer}, tags=["profile"])
    def post(self, request):
        if HealthProfile.objects.filter(user=request.user).exists():
            raise ProfileAlreadyExists()
        serializer = ProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save(user=request.user)
        return Response(ProfileSerializer(profile).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ProfileSerializer, responses={200: ProfileSerializer}, tags=["profile"])
    def patch(self, request):
        profile = self._get_profile(request)
        if profile.status != HealthProfile.Status.ACTIVE:
            raise PermissionDenied("Your profile is deactivated and can no longer be edited.")
        serializer = ProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
