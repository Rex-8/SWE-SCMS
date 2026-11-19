# Sprint 1 test execution summary

| | |
|---|---|
| Date | 2026-11-19 |
| Commit | 303ab58 |
| Python | Python 3.14.7 |
| Database | SQLite (this run); CI also runs PostgreSQL 15 |
| Command | python manage.py test |
| Result | **OK** |
| Tests run | 234 |
| Duration | 64.508 s |

Coverage by area: authentication, OTP, RBAC, sessions/CSRF, password handling, transport settings, audit, complaint submission, tracking IDs, tracking, routing, status workflow, closure, notifications, end-to-end lifecycle, and Sprint 2 scope guards. Requirement-to-test mapping: docs/TRACEABILITY.md.

Notes: "Notification delivery failed" lines in the test output are expected (tests simulate provider failures). The CI run on the release PR is the authoritative result. Performance, availability, load, accessibility and retention targets (NF-001..NF-005) are not covered by these tests.