import pytest
from unittest.mock import patch
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status


@pytest.mark.django_db
class TestHealthCheck:
    def setup_method(self):
        self.client = APIClient()

    def test_health_check_api_v1_success(self):
        url = reverse('assets:health-check')
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "status": "healthy",
            "database": "connected"
        }

    def test_health_check_root_success(self):
        url = reverse('root-health-check')
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "status": "healthy",
            "database": "connected"
        }

    def test_health_check_database_failure(self):
        url = reverse('assets:health-check')
        with patch('django.db.connection.ensure_connection', side_effect=Exception('DB connection failed')):
            response = self.client.get(url)
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert response.json() == {
                "status": "unhealthy",
                "database": "disconnected"
            }
