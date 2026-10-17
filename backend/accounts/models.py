from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone


class UserManager(BaseUserManager):
    """Creates users. Emails are always stored lower-case."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).strip().lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # stores a secure hash, never the plain password
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """Standard self-registered user. Role is always 'user'."""
        extra_fields["role"] = User.Role.USER
        extra_fields["is_staff"] = False
        extra_fields["is_superuser"] = False
        return self._create_user(email, password, **extra_fields)

    def create_admin(self, email, password, **extra_fields):
        """Admin account. Only called from the create_admin management command."""
        extra_fields["role"] = User.Role.ADMIN
        extra_fields["is_staff"] = True
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        """Required by Django's tooling; behaves like an admin with all permissions."""
        extra_fields["is_superuser"] = True
        return self.create_admin(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        USER = "user", "User"
        ADMIN = "admin", "Admin"

    email = models.EmailField(max_length=254, unique=True)
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.USER)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        constraints = [
            # The database itself refuses an email that isn't lower-case.
            # Together with unique=True this makes email unique in any letter case.
            models.CheckConstraint(
                condition=Q(email=Lower("email")),
                name="user_email_is_lowercase",
            ),
            models.CheckConstraint(
                condition=Q(role__in=["user", "admin"]),
                name="user_role_is_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    def __str__(self):
        return f"{self.email} ({self.role})"