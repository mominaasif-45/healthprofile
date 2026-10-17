from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .authentication import CookieJWTAuthentication, enforce_csrf
from .cookies import clear_auth_cookies, set_auth_cookies
from .models import User
from .serializers import LoginSerializer, SignupSerializer, UserSerializer


class InvalidCredentials(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Invalid email or password."
    default_code = "invalid_credentials"


class SessionExpired(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Your session has expired. Please sign in again."
    default_code = "token_invalid"


class SignupView(APIView):
    """Public endpoint: anyone can create a standard user account."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=SignupSerializer, responses={201: UserSerializer}, tags=["auth"])
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserLoginView(APIView):
    """Standard users sign in here and receive JWTs in HttpOnly cookies."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"            # max 5 attempts per minute (settings.py)

    @extend_schema(request=LoginSerializer, responses={200: UserSerializer}, tags=["auth"])
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:                       # wrong password, unknown email, or inactive
            raise InvalidCredentials()
        if user.role != User.Role.USER:        # admins never get a JWT
            raise PermissionDenied("Admins must sign in through the admin portal.")

        refresh = RefreshToken.for_user(user)  # claims: user_id, exp, jti, token_type only
        update_last_login(None, user)

        response = Response(UserSerializer(user).data, status=status.HTTP_200_OK)
        set_auth_cookies(response, str(refresh.access_token), str(refresh))
        return response


class UserRefreshView(APIView):
    """Swap the refresh cookie for new tokens. The old refresh token is blacklisted."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={200: UserSerializer}, tags=["auth"])
    def post(self, request):
        enforce_csrf(request)
        raw = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if not raw:
            raise SessionExpired()
        try:
            old_refresh = RefreshToken(raw)            # fails if expired, fake or blacklisted
            user = User.objects.get(
                id=old_refresh["user_id"], is_active=True, role=User.Role.USER
            )
            old_refresh.blacklist()
        except (TokenError, User.DoesNotExist):
            raise SessionExpired()

        new_refresh = RefreshToken.for_user(user)
        response = Response(UserSerializer(user).data)
        set_auth_cookies(response, str(new_refresh.access_token), str(new_refresh))
        return response


class UserLogoutView(APIView):
    """Blacklist the refresh token and delete both cookies."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None}, tags=["auth"])
    def post(self, request):
        enforce_csrf(request)
        raw = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass  # already expired or blacklisted: still log out
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        return response


class MeView(APIView):
    """Who am I? Only works with a valid access cookie."""

    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: UserSerializer}, tags=["auth"])
    def get(self, request):
        return Response(UserSerializer(request.user).data)