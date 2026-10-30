from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.complaints.models import Category, Complaint, ComplaintStatus, Department


def make_user(role, n=1):
    # No password: the user gets an unusable one, so there is no credential in the tests.
    return User.objects.create_user(email=f"{role.lower()}{n}@example.com", name=role, role=role)


class ComplaintModelTestBase(TestCase):
    def setUp(self):
        self.citizen = make_user(Role.CITIZEN)
        self.staff = make_user(Role.STAFF)
        self.elec = Department.objects.create(name="Electricity")
        self.water = Department.objects.create(name="Water Supply")
        self.elec.staff.add(self.staff)
        self.lights = Category.objects.create(name="Streetlight", department=self.elec)

    def build(self, **kw):
        data = dict(
            tracking_id="SCMS-20261030-AAAAAA",
            citizen=self.citizen,
            category=self.lights,
            department=self.elec,
            description="Light is out",
            location="Sector 12",
        )
        data.update(kw)
        return Complaint(**data)


class DepartmentCategoryTests(ComplaintModelTestBase):
    def test_department_name_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Department.objects.create(name="Electricity")

    def test_category_department_relationship(self):
        self.assertEqual(self.lights.department, self.elec)
        self.assertIn(self.lights, self.elec.categories.all())

    def test_department_with_categories_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.elec.delete()


class ComplaintTests(ComplaintModelTestBase):
    def test_create_complaint_defaults_and_relations(self):
        c = self.build()
        c.full_clean()
        c.save()
        c.refresh_from_db()
        self.assertEqual(c.status, ComplaintStatus.SUBMITTED)
        self.assertIsNone(c.closed_at)
        self.assertEqual(c.citizen, self.citizen)
        self.assertEqual(c.category, self.lights)
        self.assertEqual(c.department, self.elec)

    def test_tracking_id_unique(self):
        self.build().save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.build().save()

    def test_tracking_id_format(self):
        for bad in ("ABC", "SCMS-20261030-abcdef", "SCMS-2026-AAAAAA", "SCMS-20261030-AAAAAAA"):
            with self.assertRaises(ValidationError):
                self.build(tracking_id=bad).full_clean()

    def test_citizen_must_have_citizen_role(self):
        with self.assertRaises(ValidationError) as cm:
            self.build(citizen=self.staff).full_clean()
        self.assertIn("citizen", cm.exception.message_dict)

    def test_department_must_match_category(self):
        with self.assertRaises(ValidationError) as cm:
            self.build(department=self.water).full_clean()
        self.assertIn("department", cm.exception.message_dict)

    def test_assigned_staff_must_be_staff_of_department(self):
        with self.assertRaises(ValidationError):
            self.build(assigned_staff=self.citizen).full_clean()
        outsider = make_user(Role.STAFF, 2)
        with self.assertRaises(ValidationError):
            self.build(assigned_staff=outsider).full_clean()
        self.build(assigned_staff=self.staff).full_clean()

    def test_invalid_status_rejected_by_db(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.build(status="BOGUS").save()

    def test_closed_requires_resolution_details_in_db(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.build(status=ComplaintStatus.CLOSED, closed_at=timezone.now()).save()

    def test_whitespace_resolution_rejected_by_clean(self):
        c = self.build(status=ComplaintStatus.CLOSED, closed_at=timezone.now(), resolution_details="  ")
        with self.assertRaises(ValidationError):
            c.full_clean()

    def test_closed_requires_closed_at_in_db(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.build(status=ComplaintStatus.CLOSED, resolution_details="Fixed").save()

    def test_closed_at_forbidden_when_not_closed_in_db(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.build(closed_at=timezone.now()).save()

    def test_valid_closed_complaint_saves(self):
        c = self.build(
            status=ComplaintStatus.CLOSED, resolution_details="Fixed", closed_at=timezone.now()
        )
        c.full_clean()
        c.save()


class FixtureTests(TestCase):
    def test_sample_fixture_loads(self):
        call_command("loaddata", "sample_departments", verbosity=0)
        self.assertEqual(Category.objects.count(), 4)
        for cat in Category.objects.select_related("department"):
            self.assertTrue(cat.department.is_active)
