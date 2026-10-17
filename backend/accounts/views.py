from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import SignupSerializer, UserSerializer


class SignupView(APIView):
    """Public endpoint: anyone can create a standard user account."""

    authentication_classes = []        # no login needed to sign up
    permission_classes = [AllowAny]

    @extend_schema(request=SignupSerializer, responses={201: UserSerializer}, tags=["auth"])
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)   # returns 400 / 409 automatically
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)