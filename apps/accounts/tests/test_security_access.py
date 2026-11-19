from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.accounts.tests.helpers import make_verified_user
from apps.complaints.tests.helpers import TRACK_URL, ComplaintAPITestCase
from apps.complaints.tests.test_status_workflow import client_for

AUTH = "/api/v1/auth"
BASE = "/api/v1/complaints"
ALL = {"citizen", "staff", "admin"}
STAFF_ONLY = {"staff", "admin"}


def call(client, method, url, payload):
    if payload is None:
        return getattr(client, method)(url)
    return getattr(client, method)(url, payload, format="json")


class EndpointRoleMatrixTests(ComplaintAPITestCase):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()

    def endpoints(self):
        c = self.complaint
        return [
            ("get", f"{AUTH}/me", None, ALL),
            ("post", f"{AUTH}/logout", None, ALL),
            ("get", f"{BASE}/categories", None, ALL),
            ("post", BASE, self.payload(), {"citizen"}),
            ("get", f"{BASE}/assigned", None, STAFF_ONLY),
            ("patch", f"{BASE}/{c.pk}/status", {"status": "In Progress"}, STAFF_ONLY),
            ("post", f"{BASE}/{c.pk}/close", {"resolutionDetails": "Fixed."}, STAFF_ONLY),
            ("get", f"{TRACK_URL}/{c.tracking_id}", None, ALL),
        ]

    def clients(self):
        return {
            "anonymous": APIClient(),
            "citizen": client_for(self.citizen),
            "staff": client_for(self.staff),
            "admin": client_for(self.admin),
        }

    def test_every_endpoint_enforces_its_roles_on_the_server(self):
        for method, url, payload, allowed in self.endpoints():
            for role, client in self.clients().items():
                with self.subTest(endpoint=f"{method.upper()} {url}", role=role):
                    status = call(client, method, url, payload).status_code
                    if role in allowed:
                        self.assertNotIn(status, (401, 403))
                    else:
                        self.assertEqual(status, 403)

    def test_django_admin_flags_do_not_grant_api_access(self):
        sneaky = make_verified_user(email="sneaky@example.com")  # CITIZEN role
        sneaky.is_staff = True
        sneaky.is_superuser = True
        sneaky.save()
        client = client_for(sneaky)
        for method, url, payload, allowed in self.endpoints():
            if "citizen" in allowed:
                continue
            with self.subTest(endpoint=f"{method.upper()} {url}"):
                self.assertEqual(call(client, method, url, payload).status_code, 403)
        self.assertEqual(client.get(f"{TRACK_URL}/{self.complaint.tracking_id}").status_code, 404)

    def test_role_changes_apply_immediately_to_existing_sessions(self):
        client = client_for(self.staff)
        self.assertEqual(client.get(f"{BASE}/assigned").status_code, 200)
        self.staff.role = Role.CITIZEN
        self.staff.save()
        self.assertEqual(client.get(f"{BASE}/assigned").status_code, 403)

    def test_object_level_access(self):
        roads_staff = make_verified_user(email="roads@example.com", role=Role.STAFF)
        self.roads.staff.add(roads_staff)
        cases = {
            "owner": (self.citizen, {"track": 200, "status": 403, "close": 403}),
            "other_citizen": (self.other_citizen, {"track": 404, "status": 403, "close": 403}),
            "other_department_staff": (roads_staff, {"track": 404, "status": 404, "close": 404}),
            "department_staff": (self.staff, {"track": 200, "status": 200, "close": 409}),
            "admin": (self.admin, {"track": 200, "status": 200, "close": 409}),
        }
        for index, (label, (user, expected)) in enumerate(cases.items()):
            complaint = self.make_complaint(tracking_id=f"SCMS-20261030-OBJ{index:03d}")
            client = client_for(user)
            responses = {
                "track": client.get(f"{TRACK_URL}/{complaint.tracking_id}"),
                "status": client.patch(
                    f"{BASE}/{complaint.pk}/status", {"status": "In Progress"}, format="json"
                ),
                "close": client.post(
                    f"{BASE}/{complaint.pk}/close", {"resolutionDetails": "Fixed."}, format="json"
                ),
            }
            for action, response in responses.items():
                with self.subTest(case=label, action=action):
                    self.assertEqual(response.status_code, expected[action])

    def test_there_are_no_replace_or_delete_endpoints(self):
        staff, citizen = client_for(self.staff), client_for(self.citizen)
        pk = self.complaint.pk
        attempts = [
            (citizen, "put", f"{AUTH}/me"),
            (citizen, "patch", f"{AUTH}/me"),
            (citizen, "delete", f"{AUTH}/me"),
            (citizen, "put", BASE),
            (citizen, "delete", BASE),
            (staff, "put", f"{BASE}/{pk}/status"),
            (staff, "delete", f"{BASE}/{pk}/status"),
            (staff, "get", f"{BASE}/{pk}/close"),
        ]
        for client, method, url in attempts:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(client, method)(url).status_code, 405)

    def test_department_staff_cannot_use_the_django_admin_site(self):
        response = client_for(self.staff).get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)
