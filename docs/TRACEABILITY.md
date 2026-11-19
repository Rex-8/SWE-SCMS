# Sprint 1 traceability

| Requirement | Implemented in | Tests |
|---|---|---|
| F-001 Registration + OTP verification | `accounts` (`services.register_citizen`, `verify_otp`) | `accounts/tests/test_registration.py` (TC-Auth-01) |
| F-002 Login / logout | `accounts` (`ContactBackend`, `LoginView`) | `accounts/tests/test_login.py` (TC-Auth-02) |
| F-003 RBAC | `accounts/permissions.py`, `complaints/permissions.py` | `accounts/tests/test_rbac.py` (TC-Auth-03), `test_security_access.py` (TC-Sec-03) |
| F-004 Complaint submission | `complaints/services.submit_complaint` | `complaints/tests/test_submission.py` (TC-Lodge-01) |
| F-006 Tracking ID | `complaints/services.generate_tracking_id` | `complaints/tests/test_tracking_id.py` (TC-Lodge-03) |
| F-007 Tracking | `tracking/` | `tracking/tests/test_tracking.py` (TC-Track-01) |
| F-010 Automatic department assignment | `routing/services.resolve_department` | `complaints/tests/test_assignment.py`, `routing/tests/test_services.py` (TC-Assign-01) |
| F-012 Status updates | `complaints/services.change_status`, `workflow.py` | `complaints/tests/test_status_workflow.py`, `test_workflow.py` (TC-Admin-01) |
| F-013 Closure | `complaints/services.close_complaint` | `complaints/tests/test_closure.py` (TC-Admin-02) |
| F-014 Notifications | `notifications/` | `notifications/tests/` (TC-Notify-01) |
| SR-001 TLS-ready config | `config/settings.py` (`DJANGO_DEBUG=False` block) | `accounts/tests/test_security_transport.py` (TC-Sec-01) |
| SR-002 Password hashing | Argon2 hasher | `accounts/tests/test_security_passwords.py` (TC-Sec-02) |
| SR-003 Server-side RBAC | see F-003 | `accounts/tests/test_security_access.py` (TC-Sec-03) |
| SR-004 Session security | session/CSRF settings | `accounts/tests/test_security_sessions.py` (TC-Sec-04) |
| SR-005 Audit logging | `audit/`, `AuditedAdminMixin` | `audit/tests/` (TC-Sec-05) |
| End-to-end lifecycle | all of the above | `tests/integration/` |

The TC-Sec-01..05 to SR-001..005 mapping is assumed; adjust to the STP numbering.

Not validated by these tests (need a deployed environment): NF-001 response time, NF-002 availability, NF-003 load, NF-004 accessibility, NF-005 five-year retention.
Sprint 2 exclusions (F-005, F-008, F-009, F-011, F-015) are guarded by `tests/integration/test_scope.py`.
