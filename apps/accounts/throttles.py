import hashlib

from rest_framework.throttling import SimpleRateThrottle


class IdentifierThrottle(SimpleRateThrottle):
    """Throttle per submitted account identifier, independent of the caller's IP."""

    identifier_fields = ("identifier",)

    def get_cache_key(self, request, view):
        data = request.data if hasattr(request.data, "get") else {}
        raw = "|".join(str(data.get(f, "")).strip().lower() for f in self.identifier_fields)
        if not raw.strip("|"):
            return None
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class RegisterIdentifierThrottle(IdentifierThrottle):
    scope = "register_identifier"
    identifier_fields = ("email", "mobile")


class LoginIdentifierThrottle(IdentifierThrottle):
    scope = "login_identifier"


class OTPIdentifierThrottle(IdentifierThrottle):
    scope = "otp_identifier"
