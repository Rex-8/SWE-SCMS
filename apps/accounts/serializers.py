from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User, _clean_email, _clean_mobile, mobile_validator


class RegisterSerializer(serializers.Serializer):
    # No `role` field: unknown input is ignored, so public registration can only create citizens.
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    mobile = serializers.CharField(
        required=False, allow_blank=True, max_length=16, validators=[mobile_validator]
    )
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate(self, attrs):
        email = _clean_email(attrs.get("email"))
        mobile = _clean_mobile(attrs.get("mobile"))
        if bool(email) == bool(mobile):
            raise serializers.ValidationError("Provide exactly one of email or mobile.")
        try:
            validate_password(attrs["password"], User(name=attrs["name"], email=email, mobile=mobile))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        attrs["email"], attrs["mobile"] = email, mobile
        return attrs


class VerifyOTPSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    otp = serializers.CharField(max_length=10)


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
