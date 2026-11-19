# SCMS: Smart Complaint Management System (Sprint 1)

![CI](https://github.com/Rex-8/SWE-SCMS/actions/workflows/ci.yml/badge.svg)

Citizens lodge complaints about public services, get a tracking ID and follow resolution. Department staff process complaints assigned to their department; admins oversee the system. Sprint 1 covers requirements F-001..F-004, F-006, F-007, F-010, F-012..F-014 (see `docs/TRACEABILITY.md`).

**Stack:** Python 3.11+, Django 5.2, Django REST Framework, SQLite (dev) / PostgreSQL 15, session authentication, Argon2 password hashing. Layered modular monolith; business rules live in `services.py` modules. Sprint 1 is API-first: there are no HTML pages yet, only the JSON API and the Django admin site.

## Setup

Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "import secrets; open('.env','w',encoding='utf-8',newline='\n').write('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(50) + '\nDJANGO_DEBUG=True\n')"
python manage.py migrate
python manage.py loaddata sample_departments
python manage.py createsuperuser
python manage.py runserver
```
Linux/macOS: `source .venv/bin/activate` instead of the activate script; the rest is identical. Never create `.env` with PowerShell `>` (it writes UTF-16 and Django will not read it).

## Configuration (`.env`, see `.env.example`)
| Variable | Purpose | Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | required | none |
| `DJANGO_DEBUG` | `True` for local HTTP; `False` enables secure cookies, HTTPS redirect and HSTS | `False` |
| `DJANGO_ALLOWED_HOSTS` | comma-separated | empty |
| `DJANGO_SECURE_SSL_REDIRECT` | redirect HTTP to HTTPS when `DEBUG=False` | `True` |
| `DATABASE_URL` | e.g. `postgres://user:pass@host:5432/db` (also `pip install -r requirements-postgres.txt`) | SQLite file |
| `OTP_GATEWAY` | dotted path of the OTP delivery class | console (DEBUG only) |
| `NOTIFICATION_ADAPTER` | dotted path of the notification adapter | console (DEBUG only) |

## Users and roles
| Role | Can |
|---|---|
| Citizen | register + verify, log in, submit complaints, track **own** complaints |
| Staff | list/track/update/close complaints of **their department** |
| Admin | everything staff can, for all departments; Django admin site |

Public registration only creates citizens. Staff and admins are provisioned by an admin:
- Admin: `python manage.py createsuperuser`.
- Staff: in `/admin/` create a user with role **Staff** and tick **Is verified** (unverified users cannot log in), then add them to a department under **Departments → Staff**.

## API (`/api/v1/`, session cookie + CSRF)
Call `GET auth/csrf` first and send the `csrftoken` cookie value as the `X-CSRFToken` header on every POST/PATCH. In development the OTP is printed to the `runserver` console.

| Method | Path | Access | Body |
|---|---|---|---|
| GET | `auth/csrf` | public | |
| POST | `auth/register` | public | `name`, exactly one of `email`/`mobile`, `password` |
| POST | `auth/verify-otp` | public | `identifier`, `otp` |
| POST | `auth/login` | public | `identifier` (email or mobile), `password` |
| POST | `auth/logout` | authenticated | |
| GET | `auth/me` | authenticated | |
| GET | `complaints/categories` | authenticated | |
| POST | `complaints` | citizen | `categoryId`, `description`, `location` |
| GET | `complaints/track/{trackingId}` | owner / department staff / admin | |
| GET | `complaints/assigned` | staff / admin | `?page=`, `?pageSize=` |
| PATCH | `complaints/{id}/status` | staff (own dept) / admin | `status`, `remark` |
| POST | `complaints/{id}/close` | staff (own dept) / admin | `resolutionDetails` |

Workflow: `Assigned → In Progress → Resolved → Closed` (`Resolved` may return to `In Progress`; `Closed` is terminal and reachable only through `close`). Unknown, malformed and not-yours complaint IDs all return the same 404. Complaints are created in status *Assigned*, with the department taken from the category.

## Notifications and audit
Every status change writes a notification row and an audit row in the same transaction; delivery happens after commit and can never undo the change. Failed deliveries are retried by running periodically:
```
python manage.py send_pending_notifications
```
The audit log is append-only (view it in `/admin/`); staff/admin actions, including Django-admin edits, are recorded.

## Tests, lint, CI
```
python manage.py test        # unit + integration (tests/integration is the end-to-end lifecycle)
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
```
GitHub Actions runs lint, tests on Python 3.12 and 3.14 (SQLite) and on PostgreSQL 15.

## Layout
`config/` settings and URLs · `apps/accounts` identity, OTP, auth · `apps/complaints` models, workflow, status/close · `apps/routing` category→department · `apps/tracking` tracking lookup · `apps/notifications` outbox + adapters · `apps/audit` append-only log · `tests/integration` · `docs/`

## Production notes
Serve over HTTPS with `DJANGO_DEBUG=False`; use PostgreSQL; configure a **shared cache** (throttle counters are per-process by default); provide real OTP and notification adapters (the console ones refuse to run when `DEBUG=False`); run `send_pending_notifications` on a schedule. See `docs/RELEASE_NOTES.md` for known limitations.

## Branching
`main` ← `develop` ← `rehaan-dev` / `meghana-dev`. Feature PRs target `develop` and need the other developer's review.
