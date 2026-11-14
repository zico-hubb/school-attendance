from .base import *  # noqa: F403
from .base import os

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() in {"1", "true", "yes"}
