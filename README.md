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
