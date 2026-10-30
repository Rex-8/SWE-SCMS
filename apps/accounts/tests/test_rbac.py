from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import (
    IsAdminRole,
    IsCitizen,
    IsDepartmentStaff,
    IsObjectOwner,
    IsStaffOrAdmin,
    is_owner,
)

from .helpers import make_verified_user


def make_view(permission):
    class View(APIView):
        permission_classes = [permission]

        def get(self, request):
            return Response({"ok": True})

    return View.as_view()


class RoleMatrixTests(TestCase):
    def setUp(self):
        self.users = {
            role: make_verified_user(email=f"{role.lower()}@example.com", role=role)
            for role in Role.values
        }
        self.rf = APIRequestFactory()

    def status_for(self, permission, user):
        request = self.rf.get("/")
        if user is not None:
            force_authenticate(request, user=user)
        return make_view(permission)(request).status_code

    def test_permission_matrix(self):
        allowed = {
            IsCitizen: {Role.CITIZEN},
            IsDepartmentStaff: {Role.STAFF},
            IsAdminRole: {Role.ADMIN},
            IsStaffOrAdmin: {Role.STAFF, Role.ADMIN},
        }
        for permission, roles in allowed.items():
            for role, user in self.users.items():
                expected = 200 if role in roles else 403
                with self.subTest(permission=permission.__name__, role=role):
                    self.assertEqual(self.status_for(permission, user), expected)

    def test_anonymous_is_denied_everywhere(self):
        for permission in (IsCitizen, IsDepartmentStaff, IsAdminRole, IsStaffOrAdmin):
            with self.subTest(permission=permission.__name__):
                self.assertEqual(self.status_for(permission, None), 403)


class OwnershipTests(TestCase):
    def setUp(self):
        self.owner = make_verified_user(email="owner@example.com")
        self.other = make_verified_user(email="other@example.com")
        self.obj = SimpleNamespace(citizen_id=self.owner.pk)

    def test_is_owner(self):
        self.assertTrue(is_owner(self.owner, self.obj))
        self.assertFalse(is_owner(self.other, self.obj))
        self.assertFalse(is_owner(AnonymousUser(), self.obj))

    def test_custom_owner_field(self):
        obj = SimpleNamespace(created_by_id=self.owner.pk)
        self.assertTrue(is_owner(self.owner, obj, "created_by"))
        self.assertFalse(is_owner(self.other, obj, "created_by"))

    def test_drf_object_permission(self):
        request = APIRequestFactory().get("/")
        request.user = self.other
        self.assertFalse(IsObjectOwner().has_object_permission(request, None, self.obj))
        request.user = self.owner
        self.assertTrue(IsObjectOwner().has_object_permission(request, None, self.obj))


class AdminSiteAccessTests(TestCase):
    def test_citizen_cannot_open_django_admin(self):
        self.client.force_login(make_verified_user(email="c@example.com"))
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)
