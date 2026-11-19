from apps.audit.models import AuditLog
from apps.complaints.models import Complaint
from apps.notifications.adapters import LocMemNotificationAdapter
from apps.notifications.models import Notification

from .helpers import TRACKING_ID_RE, IntegrationTestCase


class CitizenToResolutionTests(IntegrationTestCase):
    def test_complete_complaint_lifecycle(self):
        # 1-3. Citizen registers, verifies and logs in.
        citizen = self.sign_up("asha@example.com")
        self.assertEqual(citizen.get("/auth/me").json()["role"], "CITIZEN")

        # 4-6. Submits a complaint: tracking ID generated, department assigned from the category.
        categories = citizen.get("/complaints/categories")
        self.assertIn("Streetlight not working", [c["name"] for c in categories.json()])
        submitted = citizen.post(
            "/complaints",
            {"categoryId": self.lights.pk, "description": "Streetlight out near the park", "location": "Sector 12"},
        )
        self.assertEqual(submitted.status_code, 201)
        body = submitted.json()
        tracking_id = body["trackingId"]
        self.assertRegex(tracking_id, TRACKING_ID_RE)
        self.assertEqual((body["status"], body["department"]), ("Assigned", "Electricity"))
        complaint = Complaint.objects.get(tracking_id=tracking_id)
        self.assertEqual(complaint.citizen.email, "asha@example.com")
        self.assertEqual(complaint.department, self.electricity)

        # 7. Citizen tracks it.
        track = f"/complaints/track/{tracking_id}"
        tracked = citizen.get(track).json()
        self.assertEqual(tracked["status"], "Assigned")
        self.assertEqual(tracked["department"], "Electricity")
        self.assertEqual(tracked["description"], "Streetlight out near the park")
        self.assertEqual(tracked["location"], "Sector 12")
        self.assertIsNone(tracked["closedAt"])

        # 8. Staff of the department sees it.
        staff = self.login(self.elec_staff)
        listing = staff.get("/complaints/assigned").json()["results"]
        self.assertEqual([row["trackingId"] for row in listing], [tracking_id])
        self.assertEqual(staff.get(track).status_code, 200)

        # 9-10. Staff starts work: citizen sees it and is notified.
        url = f"/complaints/{complaint.pk}"
        response = self.commit(lambda: staff.patch(f"{url}/status", {"status": "In Progress", "remark": "Team dispatched"}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(citizen.get(track).json()["status"], "In Progress")
        self.assertEqual(len(LocMemNotificationAdapter.outbox), 1)

        # 11. Staff resolves it.
        response = self.commit(lambda: staff.patch(f"{url}/status", {"status": "Resolved"}))
        self.assertEqual(response.status_code, 200)

        # 12-13. Staff closes it with resolution details: citizen sees Closed and is notified.
        response = self.commit(
            lambda: staff.post(f"{url}/close", {"resolutionDetails": "Streetlight repaired and functionality verified."})
        )
        self.assertEqual(response.status_code, 200)
        final = citizen.get(track).json()
        self.assertEqual(final["status"], "Closed")
        self.assertIsNotNone(final["closedAt"])
        complaint.refresh_from_db()
        self.assertEqual(complaint.resolution_details, "Streetlight repaired and functionality verified.")

        # Notifications: one per change, all delivered to the citizen.
        outbox = LocMemNotificationAdapter.outbox
        self.assertEqual(len(outbox), 3)
        self.assertTrue(all(m["address"] == "asha@example.com" for m in outbox))
        self.assertTrue(all(tracking_id in m["message"] for m in outbox))
        for message, label in zip(outbox, ("In Progress", "Resolved", "Closed")):
            self.assertIn(label, message["message"])
        self.assertEqual(
            list(Notification.objects.values_list("to_status", "delivery_status")),
            [("IN_PROGRESS", "SENT"), ("RESOLVED", "SENT"), ("CLOSED", "SENT")],
        )

        # Audit trail: every staff action, attributed to the staff member.
        entries = AuditLog.objects.order_by("id")
        self.assertEqual(
            [e.action for e in entries],
            ["complaint.status_changed", "complaint.status_changed", "complaint.closed"],
        )
        self.assertTrue(all(e.actor == self.elec_staff for e in entries))

        # A closed complaint is terminal.
        reopened = self.commit(lambda: staff.patch(f"{url}/status", {"status": "In Progress"}))
        self.assertEqual(reopened.status_code, 409)
        self.assertEqual(citizen.get(track).json()["status"], "Closed")
        self.assertEqual(Notification.objects.count(), 3)


class CitizenOwnershipTests(IntegrationTestCase):
    def test_citizens_only_ever_reach_their_own_complaints(self):
        asha = self.sign_up("asha@example.com", "Asha")
        ravi = self.sign_up("ravi@example.com", "Ravi")
        asha_id = self.submit(asha)
        ravi_id = self.submit(ravi, self.potholes, "Pothole on 5th street")
        self.assertNotEqual(asha_id, ravi_id)

        self.assertEqual(asha.get(f"/complaints/track/{asha_id}").status_code, 200)
        self.assertEqual(ravi.get(f"/complaints/track/{ravi_id}").status_code, 200)

        # Another citizen's complaint looks exactly like one that does not exist.
        stolen = ravi.get(f"/complaints/track/{asha_id}")
        unknown = ravi.get("/complaints/track/SCMS-20261030-ZZZZZZ")
        self.assertEqual(stolen.status_code, 404)
        self.assertEqual(stolen.json(), unknown.json())
        self.assertEqual(asha.get(f"/complaints/track/{ravi_id}").status_code, 404)

        # Citizens cannot act on anyone's complaint, their own included.
        asha_pk = Complaint.objects.get(tracking_id=asha_id).pk
        for session in (asha, ravi):
            self.assertEqual(session.patch(f"/complaints/{asha_pk}/status", {"status": "In Progress"}).status_code, 403)
            self.assertEqual(session.post(f"/complaints/{asha_pk}/close", {"resolutionDetails": "x"}).status_code, 403)
            self.assertEqual(session.get("/complaints/assigned").status_code, 403)
        self.assertEqual(Complaint.objects.get(pk=asha_pk).status, "ASSIGNED")
        self.assertEqual(AuditLog.objects.count(), 0)


class DepartmentIsolationTests(IntegrationTestCase):
    def test_complaints_route_to_and_stay_within_their_departments(self):
        asha = self.sign_up("asha@example.com")
        electricity_id = self.submit(asha, self.lights)
        roads_id = self.submit(asha, self.potholes, "Pothole")
        elec_pk = Complaint.objects.get(tracking_id=electricity_id).pk

        elec = self.login(self.elec_staff)
        roads = self.login(self.roads_staff)
        self.assertEqual([r["trackingId"] for r in elec.get("/complaints/assigned").json()["results"]], [electricity_id])
        self.assertEqual([r["trackingId"] for r in roads.get("/complaints/assigned").json()["results"]], [roads_id])

        # Roads staff cannot see or touch an Electricity complaint.
        track = f"/complaints/track/{electricity_id}"
        self.assertEqual(roads.get(track).status_code, 404)
        self.assertEqual(roads.patch(f"/complaints/{elec_pk}/status", {"status": "In Progress"}).status_code, 404)
        self.assertEqual(roads.post(f"/complaints/{elec_pk}/close", {"resolutionDetails": "x"}).status_code, 404)
        self.assertEqual(Complaint.objects.get(pk=elec_pk).status, "ASSIGNED")
        self.assertEqual(AuditLog.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

        # Admin sees everything.
        admin = self.login(self.admin)
        self.assertEqual(admin.get("/complaints/assigned").json()["count"], 2)
        self.assertEqual(admin.get(track).status_code, 200)
