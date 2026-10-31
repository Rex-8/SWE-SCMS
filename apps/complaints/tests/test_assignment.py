from apps.complaints.models import Complaint

from .helpers import ComplaintAPITestCase


class AutomaticAssignmentTests(ComplaintAPITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.citizen)

    def test_each_category_routes_to_its_department(self):
        for category, department in ((self.lights, self.elec), (self.potholes, self.roads)):
            with self.subTest(category=category.name):
                r = self.submit(categoryId=category.pk)
                self.assertEqual(r.json()["department"], department.name)
                self.assertEqual(Complaint.objects.get(tracking_id=r.json()["trackingId"]).department, department)

    def test_remapping_a_category_affects_only_new_complaints(self):
        first = self.submit().json()["trackingId"]
        self.lights.department = self.roads
        self.lights.save()
        second = self.submit().json()
        self.assertEqual(second["department"], "Roads")
        self.assertEqual(Complaint.objects.get(tracking_id=first).department, self.elec)

    def test_no_staff_is_assigned_automatically(self):
        self.submit()
        self.assertIsNone(Complaint.objects.get().assigned_staff)
