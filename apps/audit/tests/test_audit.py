from django.contrib import admin
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase

from apps.accounts.models import Role, User
from apps.accounts.tests.helpers import make_verified_user
from apps.audit.models import AppendOnlyError, AuditLog
from apps.audit.services import record


class AuditLogTests(TestCase):
    def setUp(self):
        self.actor = make_verified_user(email="admin@example.com", role=Role.ADMIN, name="Admin")
        self.target = make_verified_user(email="target@example.com", name="Target")

    def make_entry(self, **kw):
        data = dict(actor=self.actor, action="test.action", obj=self.target, details={"a": 1})
        data.update(kw)
        return record(**data)

    def test_record_creates_entry(self):
        entry = self.make_entry()
        entry.refresh_from_db()
        self.assertEqual(entry.actor, self.actor)
        self.assertEqual(entry.action, "test.action")
        self.assertEqual(entry.object_type, "accounts.user")
        self.assertEqual(entry.object_id, str(self.target.pk))
        self.assertEqual(entry.details, {"a": 1})
        self.assertIsNotNone(entry.timestamp)

    def test_details_default_to_empty_dict(self):
        self.assertEqual(self.make_entry(details=None).details, {})

    def test_entries_cannot_be_modified(self):
        entry = self.make_entry()
        entry.action = "tampered"
        with self.assertRaises(AppendOnlyError):
            entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.action, "test.action")

    def test_entries_cannot_be_deleted(self):
        entry = self.make_entry()
        with self.assertRaises(AppendOnlyError):
            entry.delete()
        self.assertEqual(AuditLog.objects.count(), 1)

    def test_queryset_update_and_delete_are_blocked(self):
        self.make_entry()
        with self.assertRaises(AppendOnlyError):
            AuditLog.objects.all().update(action="x")
        with self.assertRaises(AppendOnlyError):
            AuditLog.objects.all().delete()
        self.assertEqual(AuditLog.objects.get().action, "test.action")

    def test_entry_rolls_back_with_the_callers_transaction(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.make_entry()
            raise RuntimeError
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_actor_with_entries_cannot_be_deleted(self):
        self.make_entry()
        with self.assertRaises(ProtectedError):
            self.actor.delete()

    def test_admin_site_is_read_only(self):
        model_admin = admin.site._registry[AuditLog]
        request = RequestFactory().get("/")
        request.user = User.objects.create_superuser(email="root@example.com", name="Root")
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
