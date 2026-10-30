from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.accounts.models import Role, User
from .helpers import PASSWORD
from apps.accounts.permissions import IsAdminRole, IsCitizen, IsStaffOrAdmin, role_required


def make(role):
    return User.objects.create_user(
        email=f"{role.lower()}@example.com", password=PASSWORD, name=role, role=role
    )


class PermissionTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.citizen = make(Role.CITIZEN)
        self.staff = make(Role.STAFF)
        self.admin = make(Role.ADMIN)

    def _req(self, user):
        r = self.rf.get("/")
        r.user = user
        return r

    def test_drf_permission_classes(self):
        self.assertTrue(IsCitizen().has_permission(self._req(self.citizen), None))
        self.assertFalse(IsCitizen().has_permission(self._req(self.staff), None))
        self.assertTrue(IsStaffOrAdmin().has_permission(self._req(self.admin), None))
        self.assertFalse(IsStaffOrAdmin().has_permission(self._req(self.citizen), None))
        self.assertFalse(IsAdminRole().has_permission(self._req(self.staff), None))
        self.assertFalse(IsAdminRole().has_permission(self._req(AnonymousUser()), None))

    def test_role_required_decorator(self):
        view = role_required(Role.STAFF, Role.ADMIN)(lambda request: HttpResponse("ok"))
        self.assertEqual(view(self._req(self.staff)).status_code, 200)
        with self.assertRaises(PermissionDenied):
            view(self._req(self.citizen))
        self.assertEqual(view(self._req(AnonymousUser())).status_code, 302)
