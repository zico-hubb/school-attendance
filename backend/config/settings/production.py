from .base import *  # noqa: F403
from .base import os

DEBUG = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

if SECRET_KEY == "unsafe-local-only-secret-key":  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY must be configured in production.")

if "DJANGO_ALLOWED_HOSTS" not in os.environ:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must be configured in production.")

if "DJANGO_CORS_ALLOWED_ORIGINS" not in os.environ:
    raise RuntimeError("DJANGO_CORS_ALLOWED_ORIGINS must be configured in production.")
