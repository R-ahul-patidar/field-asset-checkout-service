import pytest
from datetime import date, timedelta
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token

from assets.models import Asset, Employee, CheckOut


@pytest.mark.django_db
class TestAssetAPI:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="adminuser",
            password="adminpassword123"
        )
        self.token = Token.objects.create(user=self.user)
        self.auth_headers = {'HTTP_AUTHORIZATION': f'Token {self.token.key}'}

    def test_unauthenticated_access_denied(self):
        list_url = reverse('assets:asset-list')
        response = self.client.get(list_url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        post_response = self.client.post(list_url, {
            "asset_tag": "CAM-001",
            "name": "Sony FX3",
            "category": "CAMERA",
            "purchase_date": "2024-01-15"
        })
        assert post_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_asset_success(self):
        url = reverse('assets:asset-list')
        payload = {
            "asset_tag": "CAM-101",
            "name": "Sony Alpha 7 IV",
            "category": "CAMERA",
            "purchase_date": "2024-05-10"
        }
        response = self.client.post(url, payload, **self.auth_headers)
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["asset_tag"] == "CAM-101"
        assert data["status"] == "AVAILABLE"
        assert data["current_holder"] is None
        assert "id" in data

    def test_create_asset_validation_failure(self):
        url = reverse('assets:asset-list')
        Asset.objects.create(
            asset_tag="CAM-101",
            name="Existing Camera",
            category=Asset.Category.CAMERA,
            purchase_date=date(2024, 1, 1)
        )
        # Duplicate asset_tag
        payload = {
            "asset_tag": "CAM-101",
            "name": "Another Camera",
            "category": "CAMERA",
            "purchase_date": "2024-05-10"
        }
        response = self.client.post(url, payload, **self.auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "asset_tag" in response.json()

        # Invalid category
        payload_invalid_cat = {
            "asset_tag": "CAM-102",
            "name": "Invalid Category Asset",
            "category": "ROCKET",
            "purchase_date": "2024-05-10"
        }
        response = self.client.post(url, payload_invalid_cat, **self.auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_assets_pagination(self):
        url = reverse('assets:asset-list')
        # Create 25 assets to test 20 items pagination
        for i in range(25):
            Asset.objects.create(
                asset_tag=f"LAP-{i:03d}",
                name=f"Laptop {i}",
                category=Asset.Category.LAPTOP,
                purchase_date=date(2024, 1, 1)
            )

        response = self.client.get(url, **self.auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == 25
        assert len(data["results"]) == 20
        assert data["next"] is not None
        assert data["previous"] is None

    def test_filter_assets_by_status_and_category(self):
        url = reverse('assets:asset-list')
        Asset.objects.create(
            asset_tag="LAP-001",
            name="MacBook Pro",
            category=Asset.Category.LAPTOP,
            status=Asset.Status.AVAILABLE,
            purchase_date=date(2024, 1, 1)
        )
        Asset.objects.create(
            asset_tag="CAM-001",
            name="Sony Camera",
            category=Asset.Category.CAMERA,
            status=Asset.Status.CHECKED_OUT,
            purchase_date=date(2024, 1, 1)
        )
        Asset.objects.create(
            asset_tag="SEN-001",
            name="Sensor A",
            category=Asset.Category.SENSOR,
            status=Asset.Status.MAINTENANCE,
            purchase_date=date(2024, 1, 1)
        )

        # Filter by status
        resp_status = self.client.get(f"{url}?status=CHECKED_OUT", **self.auth_headers)
        assert resp_status.status_code == status.HTTP_200_OK
        data_status = resp_status.json()
        assert data_status["count"] == 1
        assert data_status["results"][0]["asset_tag"] == "CAM-001"

        # Filter by category
        resp_cat = self.client.get(f"{url}?category=LAPTOP", **self.auth_headers)
        assert resp_cat.status_code == status.HTTP_200_OK
        data_cat = resp_cat.json()
        assert data_cat["count"] == 1
        assert data_cat["results"][0]["asset_tag"] == "LAP-001"

    def test_search_assets_by_name_and_tag(self):
        url = reverse('assets:asset-list')
        Asset.objects.create(
            asset_tag="DRN-001",
            name="Phantom Drone Survey",
            category=Asset.Category.VEHICLE,
            purchase_date=date(2024, 1, 1)
        )
        Asset.objects.create(
            asset_tag="CAM-999",
            name="High Res Camera",
            category=Asset.Category.CAMERA,
            purchase_date=date(2024, 1, 1)
        )

        # Search by tag
        resp_tag = self.client.get(f"{url}?search=DRN-001", **self.auth_headers)
        assert resp_tag.status_code == status.HTTP_200_OK
        assert resp_tag.json()["count"] == 1
        assert resp_tag.json()["results"][0]["name"] == "Phantom Drone Survey"

        # Search by name substring
        resp_name = self.client.get(f"{url}?search=Camera", **self.auth_headers)
        assert resp_name.status_code == status.HTTP_200_OK
        assert resp_name.json()["count"] == 1
        assert resp_name.json()["results"][0]["asset_tag"] == "CAM-999"

    def test_retrieve_asset_with_current_holder(self):
        emp = Employee.objects.create(
            employee_code="EMP101",
            full_name="Sarah Connor",
            email="sarah@example.com"
        )
        available_asset = Asset.objects.create(
            asset_tag="LAP-100",
            name="ThinkPad P1",
            category=Asset.Category.LAPTOP,
            status=Asset.Status.AVAILABLE,
            purchase_date=date(2024, 1, 1)
        )
        checked_out_asset = Asset.objects.create(
            asset_tag="CAM-200",
            name="Red Komodo",
            category=Asset.Category.CAMERA,
            status=Asset.Status.CHECKED_OUT,
            purchase_date=date(2024, 1, 1)
        )
        CheckOut.objects.create(
            asset=checked_out_asset,
            employee=emp,
            due_at=timezone.now() + timedelta(days=5)
        )

        # Detail of available asset
        url_avail = reverse('assets:asset-detail', kwargs={'pk': available_asset.id})
        resp_avail = self.client.get(url_avail, **self.auth_headers)
        assert resp_avail.status_code == status.HTTP_200_OK
        assert resp_avail.json()["current_holder"] is None

        # Detail of checked out asset
        url_co = reverse('assets:asset-detail', kwargs={'pk': checked_out_asset.id})
        resp_co = self.client.get(url_co, **self.auth_headers)
        assert resp_co.status_code == status.HTTP_200_OK
        holder = resp_co.json()["current_holder"]
        assert holder is not None
        assert holder["employee_code"] == "EMP101"
        assert holder["name"] == "Sarah Connor"
