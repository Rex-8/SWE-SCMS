from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import services
from .serializers import LoginSerializer, RegisterSerializer, VerifyOTPSerializer
from .throttles import LoginIdentifierThrottle, OTPIdentifierThrottle, RegisterIdentifierThrottle


def _user_payload(user):
    return {"id": user.pk, "name": user.name, "role": user.role}


@method_decorator(csrf_protect, name="dispatch")
class PublicAPIView(APIView):
    """Unauthenticated endpoints. DRF skips CSRF for anonymous callers, so enforce it here."""

    authentication_classes = []
    permission_classes = [AllowAny]


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"detail": "CSRF cookie set."})


class RegisterView(PublicAPIView):
    throttle_classes = [ScopedRateThrottle, RegisterIdentifierThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            channel = services.register_citizen(**serializer.validated_data)
        except services.DuplicateAccount:
            return Response(
                {"detail": "An account with this contact already exists or is awaiting verification."},
                status=status.HTTP_409_CONFLICT,
            )
        except services.OTPDeliveryError:
            return Response(
                {"detail": "Could not send the verification code. Try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"detail": "Verification code sent.", "channel": channel}, status=status.HTTP_201_CREATED
        )


class VerifyOTPView(PublicAPIView):
    throttle_classes = [ScopedRateThrottle, OTPIdentifierThrottle]
    throttle_scope = "otp"

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.verify_otp(
                identifier=serializer.validated_data["identifier"],
                code=serializer.validated_data["otp"],
            )
        except services.InvalidOTP:
            return Response({"detail": "Invalid or expired code."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Account verified. You can now log in."})


class LoginView(PublicAPIView):
    throttle_classes = [ScopedRateThrottle, LoginIdentifierThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request._request,
            username=serializer.validated_data["identifier"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        login(request._request, user)  # rotates the session key
        return Response(_user_payload(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]  # default SessionAuthentication enforces CSRF

    def post(self, request):
        logout(request._request)
        return Response({"detail": "Logged out."})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_user_payload(request.user))
