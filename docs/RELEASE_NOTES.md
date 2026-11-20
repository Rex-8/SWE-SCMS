# SCMS Sprint 1 release notes

## Delivered
F-001 registration with OTP verification · F-002 login/logout · F-003 role-based access control · F-004 complaint submission · F-006 unique tracking IDs (`SCMS-YYYYMMDD-XXXXXX`, database-enforced, collision retry) · F-007 tracking · F-010 automatic department assignment (configurable Category→Department) · F-012 status updates with enforced transitions · F-013 closure with mandatory resolution details · F-014 citizen notifications (adapter + persistent outbox + retries).
Security: Argon2 hashing, server-side RBAC with object-level checks, CSRF everywhere, 15-minute idle sessions, HttpOnly/SameSite cookies, secure cookies/HSTS/HTTPS redirect when `DJANGO_DEBUG=False`, OTP expiry + attempt limit, login/registration/OTP throttling, append-only audit log (SR-005). Traceability: `docs/TRACEABILITY.md`. Test results: `docs/TEST_SUMMARY.md`.

## Behaviour decisions to be aware of
- Complaints are created as *Assigned*; routing is synchronous. Allowed transitions: Assigned → In Progress → Resolved → Closed, plus Resolved → In Progress. Closed is terminal. (Derived from the brief; confirm against the SAD workflow diagram.)
- Remarks on status updates are stored in the audit entry, not on the complaint.
- Access to another user's complaint returns 404, not 403.
- `assigned_staff` is never set in Sprint 1 (no reassignment, F-011).
- The sample category→department data is illustrative; the official mapping is an open team decision.

## Known limitations / follow-ups
- No HTML pages: the system is operated through the JSON API and the Django admin.
- Production OTP and notification delivery need real provider adapters; the console adapters refuse to run when `DEBUG=False`.
- Throttle counters are per-process; configure a shared cache in production.
- NF-001 performance, NF-002 availability, NF-003 load, NF-004 accessibility and NF-005 five-year retention are **not validated** by the automated tests.
- SLA management and SLA hours are unresolved.

## Excluded (Sprint 2)
F-005 evidence uploads, F-008 status history, F-009 search/filtering, F-011 admin reassignment, F-015 reports and feedback. `tests/integration/test_scope.py` guards against them appearing early.


## Full application feature completion

The role-based web application and Sprint 2 functional features have now been added while retaining the original Django/DRF services and existing tests. Added functionality:

- F-005: image/PDF evidence upload (JPG, PNG, PDF; maximum 5 MB per file; up to five files per submission) with authenticated downloads and complaint-level access checks.
- F-008: append-only chronological status history with actor, timestamp and remark, including the initial assignment.
- F-009: role-scoped search by tracking ID, category, status and date.
- F-011: admin reassignment to an active department and optional department member, with audit entry.
- F-015: admin complaint summaries/SLA breach reporting and one-time citizen rating/comment after closure.
- Responsive citizen, staff and admin dashboards; notifications; admin management of users, departments, categories and SLA hours through Django admin.

Category SLA target defaults to 72 hours and is editable by an admin. The project still requires a configured real OTP/notification provider for production. Automated Django tests could not be executed in the packaging environment because Django dependencies were not installed and package-network access was unavailable.
