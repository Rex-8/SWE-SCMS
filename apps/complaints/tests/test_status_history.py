from unittest import mock

from apps.complaints.models import Complaint, ComplaintStatus as S
from apps.complaints.services import InvalidTransition, change_status, close_complaint

from .helpers import ComplaintAPITestCase
from .state import force_state


class ComplaintStatusHistoryTests(ComplaintAPITestCase):
    def test_submission_creates_initial_history_entry(self):
        self.client.force_login(self.citizen)
        response = self.submit()
        self.assertEqual(response.status_code, 201)

        complaint = Complaint.objects.get(tracking_id=response.json()["trackingId"])
        entry = complaint.status_history.get()
        self.assertIsNone(entry.from_status)
        self.assertEqual(entry.to_status, S.ASSIGNED)
        self.assertEqual(entry.actor, self.citizen)
        self.assertEqual(entry.remark, "")
        self.assertEqual(entry.created_at, complaint.created_at)

    def test_forward_transitions_and_rework_are_recorded_in_order(self):
        complaint = self.make_complaint()
        transitions = [
            (S.IN_PROGRESS, "Work started"),
            (S.RESOLVED, "Repair completed"),
            (S.IN_PROGRESS, "Issue returned"),
            (S.RESOLVED, "Repair verified"),
        ]

        with mock.patch("apps.complaints.services.notify_status_change"):
            for new_status, remark in transitions:
                change_status(
                    complaint_id=complaint.pk,
                    actor=self.staff,
                    new_status=new_status,
                    remark=remark,
                )

        entries = list(complaint.status_history.all())
        self.assertEqual(
            [(entry.from_status, entry.to_status) for entry in entries],
            [
                (None, S.ASSIGNED),
                (S.ASSIGNED, S.IN_PROGRESS),
                (S.IN_PROGRESS, S.RESOLVED),
                (S.RESOLVED, S.IN_PROGRESS),
                (S.IN_PROGRESS, S.RESOLVED),
            ],
        )
        self.assertEqual([entry.remark for entry in entries[1:]], [item[1] for item in transitions])
        self.assertTrue(all(entry.actor == self.staff for entry in entries[1:]))

    def test_closure_records_resolution_details_as_remark(self):
        complaint = self.make_complaint()
        force_state(complaint, S.RESOLVED)

        with mock.patch("apps.complaints.services.notify_status_change"):
            close_complaint(
                complaint_id=complaint.pk,
                actor=self.staff,
                resolution_details="  Streetlight repaired.  ",
            )

        entry = complaint.status_history.latest("created_at", "id")
        self.assertEqual(entry.from_status, S.RESOLVED)
        self.assertEqual(entry.to_status, S.CLOSED)
        self.assertEqual(entry.actor, self.staff)
        self.assertEqual(entry.remark, "Streetlight repaired.")

    def test_invalid_transition_does_not_create_history(self):
        complaint = self.make_complaint()
        before = complaint.status_history.count()

        with self.assertRaises(InvalidTransition):
            change_status(
                complaint_id=complaint.pk,
                actor=self.staff,
                new_status=S.RESOLVED,
            )

        self.assertEqual(complaint.status_history.count(), before)

    def test_history_rolls_back_when_a_later_operation_fails(self):
        complaint = self.make_complaint()
        before = complaint.status_history.count()

        with (
            mock.patch("apps.complaints.services.record_audit", side_effect=RuntimeError("audit failed")),
            mock.patch("apps.complaints.services.notify_status_change"),
            self.assertRaises(RuntimeError),
        ):
            change_status(
                complaint_id=complaint.pk,
                actor=self.staff,
                new_status=S.IN_PROGRESS,
                remark="Should roll back",
            )

        complaint.refresh_from_db()
        self.assertEqual(complaint.status, S.ASSIGNED)
        self.assertEqual(complaint.status_history.count(), before)
