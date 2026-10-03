# MarketMoo API

Django 5 and Django REST Framework backend for the MarketMoo Android app and the manager dashboard.
50 automated tests: `python manage.py test` (tests never touch the real database; the `.env` file is skipped while testing).

## Configuration
Copy `.env.example` to `.env` and fill it in. **Never commit `.env`** (it is in `.gitignore`).

| Variable | Meaning |
|---|---|
| `MARKETMOO_SECRET_KEY` | Long random string (required unless `MARKETMOO_DEBUG=1`) |
| `MARKETMOO_DEBUG` | `1` for local development only. Also makes the one-time code appear in the API response (`dev_code`) |
| `DATABASE_URL` | PostgreSQL URL (Neon). Empty means local SQLite |
| `B2_KEY_ID`, `B2_APP_KEY`, `B2_BUCKET`, `B2_S3_ENDPOINT`, `B2_REGION` | Backblaze B2 (S3-compatible). Empty means files stay on local disk |
| `MARKETMOO_CORS_ORIGINS` | Comma-separated dashboard origins allowed to call the API |
| `MARKETMOO_SMS_BACKEND` | Dotted path to a class with `send(phone, text)`. The default only logs |

## Run locally (Windows, from this folder)
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py seed_demo
.venv\Scripts\python manage.py register_packs ..\build\results\packs --pack-version 2026.10.02
.venv\Scripts\python manage.py createsuperuser --phone +263770000000 --username manager
.venv\Scripts\python manage.py runserver 0.0.0.0:8000
```
To try things without touching your real database, point `MARKETMOO_ENV_FILE` at a small env file with `MARKETMOO_DEBUG=1`, a secret key and no `DATABASE_URL`.
From the Android emulator the server is `http://10.0.2.2:8000`.

## Endpoints
| Method and path | Auth | Purpose |
|---|---|---|
| `GET /v1/ping` | none | 1-byte health check; wakes a sleeping free-tier server |
| `POST /v1/auth/otp/request`, `/verify` | none | Phone sign-in; returns a token |
| `POST /v1/auth/staff-login` | none | Dashboard sign-in (staff or admin-role accounts only, throttled) |
| `GET/PATCH/DELETE /v1/auth/me` | token | Profile; delete my data |
| `POST /v1/sync`, `GET /v1/sync?since=` | token | Idempotent push of `record`, `listing`, `outbreak_report` operations; delta pull |
| `POST /v1/photos/presign` | token | Short-lived URL to upload a listing photo straight to B2 |
| `GET /v1/listings?near=lat,lon&radius=&species=&data_saver=1` | none | Live listings, nearest first (blurred positions; photo URLs unless data saver) |
| `GET /v1/listings/mine` | token | My listings with server status |
| `GET /v1/pools`, `POST /v1/pools/{id}/commitments` | none / token | Pools; server-authoritative commitments (409 when closed) |
| `GET /v1/outbreaks/active`, `/zone-check?lat=&lon=` | none | Area-level notices; zone test |
| `POST/GET /v1/outbreak-reports` | token | Suspected outbreaks, private to the reporter |
| `GET /v1/packs/manifest`, `/packs/{id}/download` | none | Pack list with size and sha256; presigned B2 URL (or local download with Range support) |
| `/v1/manager/*` | staff | Dashboard: stats, listings, users, reports, outbreaks, pools, packs |

## Rules enforced and tested
- Passwordless farmer accounts; one-time codes are stored as keyed hashes, expire, lock after 5 wrong tries, and are limited per number and per IP. No national ID.
- Every sync operation has a client UUID; replays return `duplicate`. Operation ids and records cannot be taken over by another user.
- Listings always arrive `pending`; a manager approves them. Editing a live listing sends it back to moderation. The phone number comes from the account.
- Only blurred positions (about 1 km) are stored; positions outside Zimbabwe are rejected. Photo keys must match the user and listing.
- Outbreak notices are area-level (centres rounded to 0.1 degree) and only verified notices are public. Farmer reports never become public automatically.
- Manager endpoints reject farmer tokens (403).

## Deploy (Render, with Neon and Backblaze B2)
`render.yaml` is a blueprint. Set `DATABASE_URL`, `B2_*`, `MARKETMOO_SECRET_KEY`, `MARKETMOO_ALLOWED_HOSTS` and `MARKETMOO_CORS_ORIGINS` in the Render dashboard (never in the repository).
Free Render services sleep when idle, so the first request can take a while; the app uses a 60 s read timeout and retries with backoff.

## Not built yet
Celery workers (outbreak alert fan-out by push or SMS), a real SMS gateway, experts/finance/price endpoints, PostGIS (positions are plain latitude and longitude with bounding-box and haversine filtering, enough for the trial).
