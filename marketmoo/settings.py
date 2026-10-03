"""MarketMoo API settings (school-trial backend).

Everything environment-specific comes from environment variables (see .env.example). Defaults are safe for
local development only: DEBUG is off unless MARKETMOO_DEBUG=1 and the secret key must be set in production.
"""
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv():
    """Minimal .env loader (no dependency). Skipped when running tests so they never touch the real database."""
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        return
    path = Path(os.environ.get("MARKETMOO_ENV_FILE", BASE_DIR / ".env"))
    if not path.exists():
        return
    for line in path.read_text(encoding="utf8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

DEBUG = os.environ.get("MARKETMOO_DEBUG", "0") == "1"

SECRET_KEY = os.environ.get("MARKETMOO_SECRET_KEY", "")
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
if not SECRET_KEY:
    if DEBUG or TESTING:
        SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"
    else:
        raise RuntimeError("Set MARKETMOO_SECRET_KEY (or MARKETMOO_DEBUG=1 for local development).")

ALLOWED_HOSTS = [h for h in os.environ.get("MARKETMOO_ALLOWED_HOSTS", "localhost,127.0.0.1,10.0.2.2").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "accounts",
    "market",
    "records",
    "health",
    "packs",
    "syncapi",
    "manager",
    "farms",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "marketmoo.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ]},
    },
]
WSGI_APPLICATION = "marketmoo.wsgi.application"
ASGI_APPLICATION = "marketmoo.asgi.application"


def _database():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    u = urlparse(url)
    if u.scheme in ("postgres", "postgresql", "postgis"):
        # Supabase / any PostgreSQL. Needs `psycopg[binary]` (listed in requirements.txt).
        return {
            "ENGINE": "django.db.backends.postgresql", "NAME": u.path.lstrip("/"), "USER": u.username, "PASSWORD": u.password,
            "HOST": u.hostname, "PORT": u.port or 5432, "CONN_MAX_AGE": 60,
            # keep libpq options from the URL (Neon needs sslmode and channel_binding)
            "OPTIONS": {"sslmode": "require", **{k: v for k, v in parse_qsl(u.query) if k in ("sslmode", "channel_binding")}},
        }
    raise RuntimeError(f"Unsupported DATABASE_URL scheme: {u.scheme}")


DATABASES = {"default": _database()}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = []  # accounts are passwordless (phone and one-time code)

LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Harare"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "600/min", "otp": "20/hour", "otp_verify": "30/hour", "staff_login": "10/hour"},
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"] + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
}

# --- MarketMoo settings
OTP_TTL_SECONDS = 600
OTP_MAX_ATTEMPTS = 5
# Development only: return the one-time code in the API response instead of sending an SMS.
OTP_DEV_ECHO = DEBUG and os.environ.get("MARKETMOO_OTP_DEV_ECHO", "1") == "1"
SMS_BACKEND = os.environ.get("MARKETMOO_SMS_BACKEND", "accounts.sms.ConsoleSmsBackend")
PACK_DIR = Path(os.environ.get("MARKETMOO_PACK_DIR", BASE_DIR / "packfiles"))

if not DEBUG and not TESTING:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.environ.get("MARKETMOO_SSL_REDIRECT", "1") == "1"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000

# --- Dashboard (React on Vercel or localhost) calls this API from the browser
CORS_ALLOWED_ORIGINS = [o for o in os.environ.get("MARKETMOO_CORS_ORIGINS", "http://localhost:5173").split(",") if o]
CORS_ALLOW_HEADERS = ["authorization", "content-type", "accept"]

# --- Backblaze B2 (S3-compatible API) for photos and downloadable packs. Empty key means local disk (development).
B2_KEY_ID = os.environ.get("B2_KEY_ID", "")
B2_APP_KEY = os.environ.get("B2_APP_KEY", "")
B2_BUCKET = os.environ.get("B2_BUCKET", "")
B2_S3_ENDPOINT = os.environ.get("B2_S3_ENDPOINT", "")
B2_REGION = os.environ.get("B2_REGION", "us-east-005")
B2_URL_TTL = 3600  # presigned URL lifetime in seconds
