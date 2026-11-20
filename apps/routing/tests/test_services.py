from django.test import TestCase

from apps.complaints.models import Category, Department
from apps.routing.services import RoutingError, resolve_department


class ResolveDepartmentTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name="Electricity")
        self.category = Category.objects.create(name="Streetlight", department=self.department)

    def test_returns_the_categorys_department(self):
        self.assertEqual(resolve_department(self.category), self.department)

    def test_follows_remapping(self):
        roads = Department.objects.create(name="Roads")
        self.category.department = roads
        self.category.save()
        self.assertEqual(resolve_department(self.category), roads)

    def test_inactive_category_rejected(self):
        self.category.is_active = False
        with self.assertRaises(RoutingError):
            resolve_department(self.category)

    def test_inactive_department_rejected(self):
        self.department.is_active = False
        with self.assertRaises(RoutingError):
            resolve_department(self.category)
