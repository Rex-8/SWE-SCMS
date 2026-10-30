from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import Role, User
from .helpers import PASSWORD


class UserModelTests(TestCase):
    def test_create_citizen_with_email(self):
        u = User.objects.create_user(email="A@Example.com", password=PASSWORD, name="A")
        self.assertEqual(u.email, "a@example.com")
        self.assertEqual(u.role, Role.CITIZEN)
        self.assertFalse(u.is_verified)

    def test_create_citizen_with_mobile_only(self):
        u = User.objects.create_user(mobile="+919876543210", password=PASSWORD, name="B")
        self.assertIsNone(u.email)
        self.assertEqual(u.mobile, "+919876543210")

    def test_requires_email_or_mobile(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(password=PASSWORD, name="C")

    def test_db_constraint_requires_contact(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(name="X", password="x")])

    def test_duplicate_email_rejected_case_insensitive(self):
        User.objects.create_user(email="d@example.com", password=PASSWORD, name="D")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(email="D@EXAMPLE.com", password=PASSWORD, name="D2")

    def test_duplicate_mobile_rejected(self):
        User.objects.create_user(mobile="9876543210", password=PASSWORD, name="E")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(mobile="9876543210", password=PASSWORD, name="E2")

    def test_empty_strings_stored_as_null(self):
        a = User.objects.create_user(email="f@example.com", mobile="", password=PASSWORD, name="F")
        b = User.objects.create_user(email="g@example.com", mobile="", password=PASSWORD, name="G")
        self.assertIsNone(a.mobile)
        self.assertIsNone(b.mobile)

    def test_password_is_hashed_with_argon2(self):
        u = User.objects.create_user(email="h@example.com", password=PASSWORD, name="H")
        self.assertNotIn(PASSWORD, u.password)
        self.assertTrue(u.password.startswith("argon2$"))
        self.assertTrue(u.check_password(PASSWORD))

    def test_roles_stored(self):
        for role in Role.values:
            u = User.objects.create_user(
                email=f"{role.lower()}@example.com", password=PASSWORD, name=role, role=role
            )
            u.refresh_from_db()
            self.assertEqual(u.role, role)

    def test_staff_role_is_pre_verified(self):
        s = User.objects.create_user(
            email="s@example.com", password=PASSWORD, name="S", role=Role.STAFF
        )
        self.assertTrue(s.is_verified)

    def test_create_superuser(self):
        u = User.objects.create_superuser(email="root@example.com", password=PASSWORD, name="Root")
        self.assertEqual(u.role, Role.ADMIN)
        self.assertTrue(u.is_staff and u.is_superuser and u.is_verified)
