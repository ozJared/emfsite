import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env():
    """Tiny .env reader so no extra package is needed."""
    f = BASE_DIR / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
env = os.environ.get
flag = lambda k, d="0": env(k, d).lower() in ("1", "true", "yes", "on")

DEBUG = flag("DEBUG", "0")
SECRET_KEY = env("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key"
    else:
        raise ImproperlyConfigured("Set SECRET_KEY in .env (setup script does this for you).")

EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_USE_TLS = flag("EMAIL_USE_TLS", "1")
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL") or EMAIL_HOST_USER or "webmaster@localhost"
EMAIL_TIMEOUT = 10
EMAIL_BACKEND = ("django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST else
                 "django.core.mail.backends.console.EmailBackend" if DEBUG else
                 "django.core.mail.backends.smtp.EmailBackend")

PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", "")
PAYSTACK_MODE = env("PAYSTACK_MODE", "test").lower()
PAYSTACK_CURRENCY = env("PAYSTACK_CURRENCY", "NGN").upper()
PAYSTACK_API_BASE = "https://api.paystack.co"
PAYSTACK_TIMEOUT = 15
ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
if ".vercel.app" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(".vercel.app")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
TRUST_PROXY = flag("TRUST_PROXY", "0")  # set to 1 behind Caddy/nginx so the real visitor IP is used

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "core",
]
if env("CLOUDINARY_URL"):
    INSTALLED_APPS.append("cloudinary_storage")
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SiteMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "core.context.site",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

database_url = env("DATABASE_URL") or env("POSTGRES_URL")
if database_url:
    DATABASES = {"default": dj_database_url.parse(
        database_url,
        conn_max_age=0,
        conn_health_checks=True,
        ssl_require=True,
    )}
elif env("POSTGRES_DB"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"), "USER": env("POSTGRES_USER", "postgres"),
        "PASSWORD": env("POSTGRES_PASSWORD", ""), "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"), "CONN_MAX_AGE": 60,
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

# File-based cache is shared by all gunicorn workers (used for login rate limiting).
CACHES = {"default": {"BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                      "LOCATION": str(BASE_DIR / ".cache")}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "/login/"
LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Lagos"
USE_I18N = False
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
if env("CLOUDINARY_URL"):
    STORAGES["default"] = {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    }
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

# Security
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SESSION_COOKIE_SECURE = flag("HTTPS", "1")
    CSRF_COOKIE_SECURE = flag("HTTPS", "1")
    if flag("HTTPS", "1"):
        SECURE_HSTS_SECONDS = 31536000
        SECURE_SSL_REDIRECT = flag("SSL_REDIRECT", "0")
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
