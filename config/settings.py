import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me-before-deployment")
DEBUG = os.getenv("DEBUG", "True").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [x.strip() for x in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "pages"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware", "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND":"django.template.backends.django.DjangoTemplates", "DIRS":[BASE_DIR / "templates"], "APP_DIRS":True, "OPTIONS":{"context_processors":["django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
database_url = os.getenv("DATABASE_URL", "")
if database_url.startswith(("postgres://", "postgresql://")):
    parsed = urlparse(database_url)
    DATABASES = {"default":{"ENGINE":"django.db.backends.postgresql", "NAME":parsed.path.lstrip("/"), "USER":parsed.username, "PASSWORD":parsed.password, "HOST":parsed.hostname, "PORT":parsed.port or 5432, "OPTIONS":{"sslmode":os.getenv("DB_SSLMODE","prefer")}, "CONN_MAX_AGE":60}}
elif os.getenv("DB_HOST"):
    DATABASES = {"default":{"ENGINE":"django.db.backends.postgresql", "NAME":os.getenv("DB_NAME","forma"), "USER":os.getenv("DB_USER","forma"), "PASSWORD":os.getenv("DB_PASSWORD",""), "HOST":os.getenv("DB_HOST"), "PORT":os.getenv("DB_PORT","5432"), "CONN_MAX_AGE":60}}
else:
    DATABASES = {"default":{"ENGINE":"django.db.backends.sqlite3", "NAME":BASE_DIR / "db.sqlite3"}}
AUTH_PASSWORD_VALIDATORS = [{"NAME":"django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},{"NAME":"django.contrib.auth.password_validation.MinimumLengthValidator"},{"NAME":"django.contrib.auth.password_validation.CommonPasswordValidator"},{"NAME":"django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE="en-us"; TIME_ZONE="UTC"; USE_I18N=True; USE_TZ=True
STATIC_URL="static/"; STATIC_ROOT=BASE_DIR / "staticfiles"; STATICFILES_DIRS=[BASE_DIR / "static"]
MEDIA_URL="/media/"; MEDIA_ROOT=BASE_DIR / "media"
STATICFILES_STORAGE="whitenoise.storage.CompressedManifestStaticFilesStorage" if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage"
DEFAULT_AUTO_FIELD="django.db.models.BigAutoField"; LOGIN_URL="login"; LOGIN_REDIRECT_URL="home"; LOGOUT_REDIRECT_URL="login"
SESSION_COOKIE_HTTPONLY=True; CSRF_COOKIE_HTTPONLY=True; SECURE_CONTENT_TYPE_NOSNIFF=True; X_FRAME_OPTIONS="DENY"
if not DEBUG:
    SECURE_SSL_REDIRECT=os.getenv("SECURE_SSL_REDIRECT","True").lower()=="true"
    SESSION_COOKIE_SECURE=True; CSRF_COOKIE_SECURE=True
    SECURE_HSTS_SECONDS=int(os.getenv("SECURE_HSTS_SECONDS","31536000")); SECURE_HSTS_INCLUDE_SUBDOMAINS=True; SECURE_HSTS_PRELOAD=True
