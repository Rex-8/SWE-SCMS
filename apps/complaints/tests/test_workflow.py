from django.test import SimpleTestCase

from apps.complaints import workflow
from apps.complaints.models import ComplaintStatus as S


class WorkflowTableTests(SimpleTestCase):
    def test_every_status_has_an_entry(self):
        self.assertEqual(set(workflow.ALLOWED_TRANSITIONS), set(S.values))

    def test_closed_is_terminal(self):
        self.assertEqual(workflow.ALLOWED_TRANSITIONS[S.CLOSED.value], frozenset())

    def test_only_resolved_can_reach_closed(self):
        for old, targets in workflow.ALLOWED_TRANSITIONS.items():
            if S.CLOSED.value in targets:
                self.assertEqual(old, S.RESOLVED.value)

    def test_status_endpoint_never_closes(self):
        self.assertFalse(workflow.can_transition(S.RESOLVED.value, S.CLOSED.value))

    def test_permitted_and_forbidden_transitions(self):
        ok = [(S.ASSIGNED, S.IN_PROGRESS), (S.IN_PROGRESS, S.RESOLVED), (S.RESOLVED, S.IN_PROGRESS)]
        bad = [(S.ASSIGNED, S.RESOLVED), (S.IN_PROGRESS, S.ASSIGNED), (S.CLOSED, S.IN_PROGRESS),
               (S.ASSIGNED, S.ASSIGNED)]  # fmt: skip
        for old, new in ok:
            self.assertTrue(workflow.can_transition(old.value, new.value), (old, new))
        for old, new in bad:
            self.assertFalse(workflow.can_transition(old.value, new.value), (old, new))

    def test_parse_status(self):
        for text in ("In Progress", "in progress", "IN_PROGRESS", "  in   progress "):
            self.assertEqual(workflow.parse_status(text), S.IN_PROGRESS.value, text)
        self.assertIsNone(workflow.parse_status("nope"))
        self.assertIsNone(workflow.parse_status(""))
        self.assertIsNone(workflow.parse_status(None))
