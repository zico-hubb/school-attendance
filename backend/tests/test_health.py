import pytest
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_health_endpoint_returns_versioned_status():
    response = APIClient().get(reverse("api:health", kwargs={"version": "1"}))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1"}


def test_health_endpoint_rejects_unsupported_method():
    response = APIClient().post(reverse("api:health", kwargs={"version": "1"}))

    assert response.status_code == 405
