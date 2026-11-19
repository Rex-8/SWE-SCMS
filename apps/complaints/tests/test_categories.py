from rest_framework.test import APIClient

from apps.complaints.models import Category, Department

from .helpers import ComplaintAPITestCase

URL = "/api/v1/complaints/categories"


class CategoryListTests(ComplaintAPITestCase):
    def test_lists_only_active_categories_without_department(self):
        Category.objects.create(name="Old category", department=self.elec, is_active=False)
        dead = Department.objects.create(name="Dead", is_active=False)
        Category.objects.create(name="Orphaned", department=dead)
        self.client.force_login(self.citizen)
        r = self.client.get(URL)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual([c["name"] for c in data], ["Road damage", "Streetlight not working"])
        for item in data:
            self.assertEqual(set(item), {"id", "name", "description"})

    def test_requires_authentication(self):
        self.assertEqual(APIClient().get(URL).status_code, 403)
