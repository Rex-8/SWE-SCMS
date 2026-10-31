from apps.accounts.models import Role
from apps.accounts.permissions import is_owner


def can_view_complaint(user, complaint):
    """Owner, admin, or staff belonging to the complaint's department."""
    if not (user and user.is_authenticated):
        return False
    if user.role == Role.ADMIN:
        return True
    if user.role == Role.CITIZEN:
        return is_owner(user, complaint)
    if user.role == Role.STAFF:
        return complaint.department.staff.filter(pk=user.pk).exists()
    return False

def can_modify_complaint(user, complaint):
    """Admin, or staff belonging to the complaint's department. Citizens never."""
    if not (user and user.is_authenticated):
        return False
    if user.role == Role.ADMIN:
        return True
    if user.role == Role.STAFF:
        return complaint.department.staff.filter(pk=user.pk).exists()
    return False
