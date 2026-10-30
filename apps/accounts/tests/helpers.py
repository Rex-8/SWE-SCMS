import secrets

# Random per test run; never a hardcoded credential.
PASSWORD = secrets.token_urlsafe(16)
