# SCMS: Smart Complaint Management System (Sprint 1)

## Setup (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env     # then set DJANGO_SECRET_KEY and DJANGO_DEBUG=True
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
(Linux/macOS: `source .venv/bin/activate`, `cp .env.example .env`.)

## Tests
```
python manage.py test
```

## Config
All config is environment-driven via `.env` (see `.env.example`).
Set `DATABASE_URL=postgres://user:pass@host:5432/db` for PostgreSQL (also `pip install "psycopg[binary]"`).
With `DJANGO_DEBUG=False`, secure cookies, HTTPS redirect and HSTS are enabled.

## Branching
`main` ← `develop` ← `rehaan-dev` / `meghana-dev`. Feature PRs target `develop`.

## Sample data
```
python manage.py loaddata sample_departments
```
Illustrative only. The official category-to-department mapping is still to be agreed by the team.

## Auth API (`/api/v1/auth/`)
Session cookies + CSRF. Call `GET csrf` first and send the `csrftoken` cookie value as the `X-CSRFToken` header on every POST.

| Method | Path | Body |
|---|---|---|
| GET | `csrf` | |
| POST | `register` | `name`, one of `email`/`mobile`, `password` |
| POST | `verify-otp` | `identifier`, `otp` |
| POST | `login` | `identifier`, `password` |
| POST | `logout` | (authenticated) |
| GET | `me` | (authenticated) |

In development the OTP is printed to the `runserver` console (mock gateway).

## Complaints API (`/api/v1/`)
| Method | Path | Access | Body |
|---|---|---|---|
| GET | `complaints/categories` | authenticated | |
| POST | `complaints` | citizen | `categoryId`, `description`, `location` |
| GET | `complaints/track/{trackingId}` | owner / department staff / admin | |

## Staff/admin API (`/api/v1/complaints/`)
| Method | Path | Access | Body |
|---|---|---|---|
| GET | `assigned` | staff (own department) / admin | `?page=`, `?pageSize=` |
| PATCH | `{id}/status` | staff (own department) / admin | `status` (e.g. `"In Progress"`), `remark` |
| POST | `{id}/close` | staff (own department) / admin | `resolutionDetails` |

`{id}` is the numeric primary key. Status flow: Assigned → In Progress → Resolved → Closed (Resolved may return to In Progress). Closing is only via `close`.
