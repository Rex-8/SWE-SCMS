from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.accounts.tests.helpers import make_verified_user

from .helpers import ComplaintAPITestCase
from .test_status_workflow import client_for

URL = "/api/v1/complaints/assigned"
FIELDS = {"id", "trackingId", "category", "department", "location", "status", "createdAt", "updatedAt"}


class AssignedListTests(ComplaintAPITestCase):
    def setUp(self):
        super().setUp()
        self.elec_complaint = self.make_complaint(tracking_id="SCMS-20261030-EEEEEE")
        self.road_complaint = self.make_complaint(tracking_id="SCMS-20261030-RRRRRR", category=self.potholes)

    def tracking_ids(self, user):
        r = client_for(user).get(URL)
        self.assertEqual(r.status_code, 200)
        return [row["trackingId"] for row in r.json()["results"]]

    def test_staff_see_only_their_departments_complaints(self):
        self.assertEqual(self.tracking_ids(self.staff), ["SCMS-20261030-EEEEEE"])

    def test_staff_without_department_see_nothing(self):
        loner = make_verified_user(email="loner@example.com", role=Role.STAFF)
        self.assertEqual(self.tracking_ids(loner), [])

    def test_admin_sees_everything_newest_first(self):
        self.assertEqual(self.tracking_ids(self.admin), ["SCMS-20261030-RRRRRR", "SCMS-20261030-EEEEEE"])

    def test_row_shape(self):
        row = client_for(self.staff).get(URL).json()["results"][0]
        self.assertEqual(set(row), FIELDS)
        self.assertEqual(row["id"], self.elec_complaint.pk)

    def test_citizens_and_anonymous_are_denied(self):
        self.assertEqual(client_for(self.citizen).get(URL).status_code, 403)
        self.assertEqual(APIClient().get(URL).status_code, 403)

    def test_pagination(self):
        for i in range(25):
            self.make_complaint(tracking_id=f"SCMS-20261030-{i:06d}")
        client = client_for(self.staff)
        first = client.get(URL).json()
        self.assertEqual(first["count"], 26)
        self.assertEqual(len(first["results"]), 20)
        self.assertEqual(len(client.get(URL, {"page": 2}).json()["results"]), 6)
        self.assertEqual(len(client.get(URL, {"pageSize": 5}).json()["results"]), 5)
