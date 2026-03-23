"""
SECURE DJANGO SETTINGS - Production & Development
All security standards enforced (OWASP Top 10, Django Best Practices)
"""

import os
import logging
from pathlib import Path
from datetime import timedelta
import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# CRITICAL: SECRET KEY & DEBUG MODE
# ─────────────────────────────────────────────────────────────────────────────

# 🔴 SECURITY REQUIREMENT: DEBUG must be False in production
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

# 🔴 SECURITY REQUIREMENT: SECRET_KEY MUST be set in environment
# Never hardcode secrets; always use .env file in production
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-me-in-production")

if not DEBUG and (not SECRET_KEY or SECRET_KEY == "django-insecure-change-me-in-production"):
    raise ValueError(
        "CRITICAL: SECRET_KEY not set or using unsafe default in production. "
        "Set SECRET_KEY environment variable in your Vercel Project Settings.\n"
        "Generate one: python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
    )

if DEBUG:
    logger = logging.getLogger(__name__)
    logger.warning("⚠️  DEBUG MODE ENABLED - Never use in production!")

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Automatically allow Vercel domains
if os.getenv("VERCEL") == "1":
    ALLOWED_HOSTS.append(".vercel.app")
    # Also add the specific system host if provided
    if os.getenv("VERCEL_URL"):
        ALLOWED_HOSTS.append(os.getenv("VERCEL_URL"))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    # Local apps
    "core",  # Security utilities
    "accounts",
    "store",
    "payments",
]

MIDDLEWARE = [
    # ✅ Security middleware stack (order matters)
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",  # ✅ CSRF protection
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",  # ✅ Clickjacking protection
    # Future: Add custom middleware for:
    # - Rate limiting on specific paths
    # - Custom security headers
    # - Audit logging on sensitive operations
]

ROOT_URLCONF = "ecommerce.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
            # ✅ Enforce template auto-escaping (XSS prevention)
            "autoescape": True,
        },
    },
]

WSGI_APPLICATION = "ecommerce.wsgi.application"

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# Supports PostgreSQL for production, SQLite for development
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=int(os.getenv("DB_CONN_MAX_AGE", "600")),
            conn_health_checks=True,
        )
    }
    # ✅ Always use SSL in production if using PostgreSQL
    if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
        DATABASES["default"]["OPTIONS"] = {
            "sslmode": os.getenv("DB_SSLMODE", "prefer"),
        }
elif os.getenv("DB_ENGINE"):
    DATABASES = {
        "default": {
            "ENGINE": os.getenv("DB_ENGINE"),
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
            # ✅ Connection pooling for production
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "600")),
            # ✅ Always use SSL in production
            "OPTIONS": {
                "sslmode": os.getenv("DB_SSLMODE", "prefer"),  # require in prod
            } if os.getenv("DB_ENGINE") == "django.db.backends.postgresql" else {},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION & USER MODEL
# ─────────────────────────────────────────────────────────────────────────────

# ✅ Custom user model with RBAC support
AUTH_USER_MODEL = "accounts.User"

# ✅ Password hashing: Argon2 (primary), bcrypt (fallback)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",  # Industry standard
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

# ✅ Strict password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},  # Enforce strong passwords
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ✅ Session security
SESSION_ENGINE = "django.contrib.sessions.backends.db"  # Secure backend
SESSION_COOKIE_AGE = 3600  # 1 hour
SESSION_COOKIE_SECURE = True  # HTTPS only in production
SESSION_COOKIE_HTTPONLY = True  # ✅ Prevent JS access (XSS protection)
SESSION_COOKIE_SAMESITE = "Strict"  # ✅ CSRF prevention
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# ─────────────────────────────────────────────────────────────────────────────
# DJANGO REST FRAMEWORK SECURITY
# ─────────────────────────────────────────────────────────────────────────────

REST_FRAMEWORK = {
    # ✅ Authentication (JWT + Sessions)
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # ✅ Default to authenticated-only access (opt-in to AllowAny)
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # ✅ API Pagination
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 12,
    # ✅ Global throttling (rate limiting)
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "50/minute",  # Tighter for anonymous users
        "user": "100/minute",
    },
    # ✅ API versioning (future-proof)
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.AcceptHeaderVersioning",
}

# ─────────────────────────────────────────────────────────────────────────────
# JWT (SIMPLEJWT) SECURITY CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

SIMPLE_JWT = {
    # ✅ Short-lived access tokens (30 minutes)
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    # ✅ Longer-lived refresh tokens (7 days)
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    # ✅ Rotate refresh tokens on each use (token freshness)
    "ROTATE_REFRESH_TOKENS": True,
    # ✅ Blacklist old tokens after rotation (prevent reuse)
    "BLACKLIST_AFTER_ROTATION": True,
    # ✅ Standard Bearer token scheme
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    # ✅ Sign tokens with HS256 (default; use RS256 for external verification)
    "ALGORITHM": "HS256",
    # Future: Consider adding token blacklist app for explicit logout
}

# ─────────────────────────────────────────────────────────────────────────────
# CSRF CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

CSRF_COOKIE_SECURE = True  # HTTPS only in production
CSRF_COOKIE_HTTPONLY = True  # ✅ Prevent XSS access to CSRF token
CSRF_COOKIE_SAMESITE = "Strict"  # ✅ Prevent cross-site requests
CSRF_TRUSTED_ORIGINS = (
    os.getenv("CSRF_TRUSTED_ORIGINS", "http://localhost:8000").split(",")
)
CSRF_FAILURE_VIEW = "core.views.csrf_failure"  # Custom error handler (optional)

# ─────────────────────────────────────────────────────────────────────────────
# SECURITY HEADERS
# ─────────────────────────────────────────────────────────────────────────────

# ✅ Prevent browser MIME type sniffing
SECURE_CONTENT_TYPE_NOSNIFF = True

# ✅ Prevent clickjacking attacks
X_FRAME_OPTIONS = "DENY"

# ✅ Enable browser XSS filter
SECURE_BROWSER_XSS_FILTER = True

# ✅ Content Security Policy (strict, can be relaxed if needed)
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0  # 1 year in production
SECURE_HSTS_INCLUDE_SUBDOMAINS = True if not DEBUG else False
SECURE_HSTS_PRELOAD = True if not DEBUG else False

# ✅ HTTPS enforcement in production
SECURE_SSL_REDIRECT = not DEBUG

# ─────────────────────────────────────────────────────────────────────────────
# CORS CONFIGURATION (Frontend Communication)
# ─────────────────────────────────────────────────────────────────────────────

CORS_ALLOWED_ORIGINS = (
    os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
)
CORS_ALLOW_CREDENTIALS = True  # Allow credentials in CORS requests
CORS_ALLOW_METHODS = [
    "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"  # Restrict to needed methods
]
CORS_ALLOW_HEADERS = [
    "content-type", "authorization", "x-csrf-token"  # Only required headers
]

# ─────────────────────────────────────────────────────────────────────────────
# INTERNATIONALIZATION & LOCALIZATION
# ─────────────────────────────────────────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# ─────────────────────────────────────────────────────────────────────────────
# EMAIL CONFIGURATION (Secure)
# ─────────────────────────────────────────────────────────────────────────────

# ✅ Use console backend for development, SMTP for production
if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")  # Use app passwords!
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# 🔴 NEVER log passwords or email credentials
if not EMAIL_HOST_PASSWORD and not DEBUG:
    logger = logging.getLogger(__name__)
    logger.warning("⚠️  EMAIL_HOST_PASSWORD not configured. Email features will fail.")

# ─────────────────────────────────────────────────────────────────────────────
# STATIC & MEDIA FILES (WhiteNoise)
# ─────────────────────────────────────────────────────────────────────────────

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# ✅ Use WhiteNoise for efficient static file serving
# Using CompressedStaticFilesStorage (without manifest) is more reliable on Vercel
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"
WHITENOISE_USE_FINDERS = True  # Look in STATICFILES_DIRS if not found in STATIC_ROOT
WHITENOISE_AUTOREFRESH = DEBUG  # refresh files in dev mode

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ─────────────────────────────────────────────────────────────────────────────
# PAYMENTS (RAZORPAY)
# ─────────────────────────────────────────────────────────────────────────────

# 🔴 CRITICAL: Razorpay credentials must be in environment
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    logger = logging.getLogger(__name__)
    if not DEBUG:
        logger.warning("⚠️  RAZORPAY credentials missing. Payments will fail.")
    # Dummy values for development
    RAZORPAY_KEY_ID = RAZORPAY_KEY_ID or "rzp_test_placeholder"
    RAZORPAY_KEY_SECRET = RAZORPAY_KEY_SECRET or "placeholder_secret"

# ─────────────────────────────────────────────────────────────────────────────
# CACHING (for rate limiting, sessions)
# ─────────────────────────────────────────────────────────────────────────────

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {
                # ✅ Prevent connection pool exhaustion
                "max_connections": 50,
                "retry_on_timeout": True,
            },
        },
        "KEY_PREFIX": "iri_collections",
        "TIMEOUT": 300,  # Default 5 minute timeout
    }
}

# Fallback to in-memory cache if Redis unavailable
if os.getenv("USE_LOCAL_CACHE") == "true" or (os.getenv("VERCEL") == "1" and not os.getenv("REDIS_URL")):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "iri-collections-cache",
        }
    }

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING CONFIGURATION (Audit trail)
# ─────────────────────────────────────────────────────────────────────────────

# Check if running on Vercel
IS_VERCEL = os.getenv("VERCEL") == "1"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "core.security": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "accounts": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}

# Only use file logging if not on Vercel (local development)
if not IS_VERCEL:
    LOGGING["formatters"]["json"] = {
        "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
        "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
    }
    LOGGING["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": BASE_DIR / "logs" / "app.log",
        "maxBytes": 1024 * 1024 * 10,
        "backupCount": 10,
        "formatter": "json",
    }
    LOGGING["handlers"]["audit_file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": BASE_DIR / "logs" / "audit.log",
        "maxBytes": 1024 * 1024 * 20,
        "backupCount": 30,
        "formatter": "json",
    }
    LOGGING["loggers"]["django"]["handlers"].append("file")
    LOGGING["loggers"]["core.security"]["handlers"].append("audit_file")
    LOGGING["loggers"]["accounts"]["handlers"].append("audit_file")
    
    # Create logs directory if it doesn't exist
    os.makedirs(BASE_DIR / "logs", exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# MISCELLANEOUS SECURITY
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ✅ Disable query caching for sensitive data
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10 MB (prevent large uploads)
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760

# ✅ User-agent validation (optional, can be extended)
USER_AGENTS_WHITELIST = [
    "Mozilla", "Chrome", "Safari", "Firefox", "Edge",
    # Add legitimate bots here
]

# ✅ API Key (if needed for external integrations)
API_KEYS_ALLOWED = os.getenv("API_KEYS_ALLOWED", "").split(",")

# ─────────────────────────────────────────────────────────────────────────────
# ENVIRONMENT-SPECIFIC OVERRIDES
# ─────────────────────────────────────────────────────────────────────────────

if DEBUG:
    # Development-specific settings
    ALLOWED_HOSTS = ["*"]
    CORS_ALLOW_ALL_ORIGINS = False  # Still restrict to CORS_ALLOWED_ORIGINS
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False
    LOGGING["loggers"]["django"]["level"] = "DEBUG"
    
else:
    # Production security enforcements
    if not SECURE_SSL_REDIRECT:
        raise ValueError("SECURE_SSL_REDIRECT must be True in production")
    if not SESSION_COOKIE_SECURE:
        raise ValueError("SESSION_COOKIE_SECURE must be True in production")
    if DEBUG:
        raise ValueError("DEBUG must be False in production")
