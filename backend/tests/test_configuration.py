import pytest
from django.conf import settings
from django.db import connection
from django.urls import resolve, reverse

from config.settings import base, development, test as test_settings

DEVELOPMENT_DATABASE_NAME = development.DATABASES["default"]["NAME"]


def test_health_route_is_in_api_v1():
    route = reverse("api:health", kwargs={"version": "1"})

    assert route == "/api/v1/health/"
    assert resolve(route).url_name == "health"


@pytest.mark.django_db
def test_postgresql_is_configured_and_tests_use_an_isolated_database():
    test_database = connection.settings_dict
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        connected_database_name = cursor.fetchone()[0]

    assert base.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert (
        development.DATABASES["default"]["ENGINE"]
        == "django.db.backends.postgresql"
    )
    assert (
        test_settings.DATABASES["default"]["ENGINE"]
        == "django.db.backends.postgresql"
    )
    assert (
        settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
    )
    assert DEVELOPMENT_DATABASE_NAME == "school_attendance"
    assert test_database["NAME"] == "test_school_attendance"
    assert test_database["NAME"] != DEVELOPMENT_DATABASE_NAME
    assert connected_database_name == test_database["NAME"]
    assert settings.STATIC_URL == "/static/"
    assert "rest_framework" in settings.INSTALLED_APPS
