from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q


class Role(models.TextChoices):
    CITIZEN = "CITIZEN", "Citizen"
    STAFF = "STAFF", "Department Staff"
    ADMIN = "ADMIN", "Admin"


mobile_validator = RegexValidator(
    r"^\+?[0-9]{10,15}$",
    "Enter a valid mobile number (10-15 digits, optional leading +).",
)


def _clean_email(value):
    return (value.strip().lower() or None) if value else None


def _clean_mobile(value):
    return (value.strip().replace(" ", "") or None) if value else None


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, mobile, password, **extra):
        email, mobile = _clean_email(email), _clean_mobile(mobile)
        if not email and not mobile:
            raise ValueError("A user needs an email address or a mobile number.")
        user = self.model(email=email, mobile=mobile, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email=None, password=None, mobile=None, **extra):
        extra.setdefault("role", Role.CITIZEN)
        extra.setdefault("is_superuser", False)
        extra.setdefault("is_staff", False)
        # Staff/Admin are provisioned by an admin, so no OTP step.
        if extra["role"] != Role.CITIZEN:
            extra.setdefault("is_verified", True)
        return self._create_user(email, mobile, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        mobile = extra.pop("mobile", None)
        extra.update(role=Role.ADMIN, is_staff=True, is_superuser=True, is_verified=True)
        return self._create_user(email, mobile, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Shared identity model for the whole project."""

    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True, null=True, blank=True)
    mobile = models.CharField(
        max_length=16, unique=True, null=True, blank=True, validators=[mobile_validator]
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CITIZEN)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # Django-admin site access only. Not the same as Role.STAFF (department staff).
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    # Email is the Django identifier; mobile login is handled by an auth backend in PR 3.
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(email__isnull=False) | Q(mobile__isnull=False),
                name="user_has_email_or_mobile",
            ),
        ]
        indexes = [models.Index(fields=["role"], name="user_role_idx")]

    def save(self, *args, **kwargs):
        # "" must never reach unique columns; emails are case-insensitive.
        self.email = _clean_email(self.email)
        self.mobile = _clean_mobile(self.mobile)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} <{self.email or self.mobile}>"

    @property
    def is_citizen(self):
        return self.role == Role.CITIZEN

    @property
    def is_department_staff(self):
        return self.role == Role.STAFF

    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN
