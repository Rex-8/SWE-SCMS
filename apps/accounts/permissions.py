from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from .models import Role


def _has_role(user, roles):
    return bool(user and user.is_authenticated and user.role in roles)


def role_required(*roles):
    """Django view decorator: login required, then role must be in `roles`."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not _has_role(request.user, roles):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


class HasRole(BasePermission):
    allowed_roles = ()

    def has_permission(self, request, view):
        return _has_role(request.user, self.allowed_roles)


class IsCitizen(HasRole):
    allowed_roles = (Role.CITIZEN,)


class IsDepartmentStaff(HasRole):
    allowed_roles = (Role.STAFF,)


class IsAdminRole(HasRole):
    allowed_roles = (Role.ADMIN,)


class IsStaffOrAdmin(HasRole):
    allowed_roles = (Role.STAFF, Role.ADMIN)

def is_owner(user, obj, field="citizen"):
    """True if `obj.<field>` is the authenticated user. Works with any model."""
    return bool(user and user.is_authenticated and getattr(obj, f"{field}_id", None) == user.pk)


class IsObjectOwner(BasePermission):
    """Object-level check. Subclass and set `owner_field` (default: `citizen`)."""

    owner_field = "citizen"

    def has_object_permission(self, request, view, obj):
        return is_owner(request.user, obj, self.owner_field)
