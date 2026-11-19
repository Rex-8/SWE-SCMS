from django.contrib.auth.backends import ModelBackend

from .models import User
from .services import find_user


class ContactBackend(ModelBackend):
    """Authenticate with email or mobile + password. Unverified/inactive users are rejected."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or password is None:
            return None
        user = find_user(username)
        if user is None:
            User().set_password(password)  # keep timing similar for unknown users
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def user_can_authenticate(self, user):
        return super().user_can_authenticate(user) and user.is_verified
