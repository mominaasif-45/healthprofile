from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from .models import User


class EmailTaken(APIException):
    """409 Conflict: this email is already registered."""
    status_code = status.HTTP_409_CONFLICT
    default_detail = "An account with this email already exists."
    default_code = "email_taken"


class UserSerializer(serializers.ModelSerializer):
    """What we send back about a user. Never includes the password."""

    class Meta:
        model = User
        fields = ["id", "name", "email", "role", "date_joined"]
        read_only_fields = fields


class SignupSerializer(serializers.Serializer):
    """
    Only these three fields are accepted. Anything else in the request
    (for example "role": "admin") is silently ignored.
    """

    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name cannot be blank.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise EmailTaken()
        return value

    def validate(self, attrs):
        # Run Django's password rules (min 10 chars, not common, not all numbers,
        # not too similar to the name/email).
        candidate = User(email=attrs.get("email"), name=attrs.get("name"))
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        try:
            return User.objects.create_user(
                email=validated_data["email"],
                password=validated_data["password"],
                name=validated_data["name"],
            )
        except IntegrityError:
            # Two signups with the same email at the exact same moment
            raise EmailTaken()