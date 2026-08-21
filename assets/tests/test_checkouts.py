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
class TestCheckOutAPI:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="adminuser",
            password="adminpassword123"
        )
        self.token = Token.objects.create(user=self.user)
        self.auth_headers = {'HTTP_AUTHORIZATION': f'Token {self.token.key}'}

        self.employee = Employee.objects.create(
            employee_code="EMP001",
            full_name="Alice Smith",
            email="alice@example.com",
            is_active=True
        )
        self.asset = Asset.objects.create(
            asset_tag="CAM-001",
            name="Sony FX3",
            category=Asset.Category.CAMERA,
            status=Asset.Status.AVAILABLE,
            purchase_date=date(2024, 1, 15)
        )
        self.checkout_url = reverse('assets:checkout-list')

    def test_checkout_success(self):
        due_at = (timezone.now() + timedelta(days=7)).isoformat()
        payload = {
            "asset_tag": "CAM-001",
            "employee_code": "EMP001",
            "due_at": due_at
        }
        response = self.client.post(self.checkout_url, payload, **self.auth_headers)
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["asset_tag"] == "CAM-001"
        assert data["employee_code"] == "EMP001"
        assert data["returned_at"] is None
        assert "id" in data

        # Verify asset status updated to CHECKED_OUT
        self.asset.refresh_from_db()
        assert self.asset.status == Asset.Status.CHECKED_OUT

        # Verify CheckOut object in database
        checkout = CheckOut.objects.get(id=data["id"])
        assert checkout.asset == self.asset
        assert checkout.employee == self.employee
        assert checkout.returned_at is None

    def test_rule_1_asset_not_available(self):
        self.asset.status = Asset.Status.CHECKED_OUT
        self.asset.save()

        due_at = (timezone.now() + timedelta(days=5)).isoformat()
        payload = {
            "asset_tag": "CAM-001",
            "employee_code": "EMP001",
            "due_at": due_at
        }
        response = self.client.post(self.checkout_url, payload, **self.auth_headers)
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "not available" in response.json()["detail"].lower()

    def test_rule_2_inactive_employee(self):
        self.employee.is_active = False
        self.employee.save()

        due_at = (timezone.now() + timedelta(days=5)).isoformat()
        payload = {
            "asset_tag": "CAM-001",
            "employee_code": "EMP001",
            "due_at": due_at
        }
        response = self.client.post(self.checkout_url, payload, **self.auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "inactive" in response.json()["detail"].lower()

    def test_rule_3_max_three_open_checkouts(self):
        # Create 3 open checkouts for employee
        for i in range(3):
            asset_i = Asset.objects.create(
                asset_tag=f"SEN-{i:03d}",
                name=f"Sensor {i}",
                category=Asset.Category.SENSOR,
                status=Asset.Status.CHECKED_OUT,
                purchase_date=date(2024, 1, 1)
            )
            CheckOut.objects.create(
                asset=asset_i,
                employee=self.employee,
                due_at=timezone.now() + timedelta(days=5)
            )

        # 4th checkout attempt must fail with 409 Conflict
        due_at = (timezone.now() + timedelta(days=5)).isoformat()
        payload = {
            "asset_tag": "CAM-001",
            "employee_code": "EMP001",
            "due_at": due_at
        }
        response = self.client.post(self.checkout_url, payload, **self.auth_headers)
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "maximum limit" in response.json()["detail"].lower()

    def test_rule_4_due_at_in_past(self):
        due_at = (timezone.now() - timedelta(days=1)).isoformat()
        payload = {
            "asset_tag": "CAM-001",
            "employee_code": "EMP001",
            "due_at": due_at
        }
        response = self.client.post(self.checkout_url, payload, **self.auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "future" in response.json()["detail"].lower()

    def test_rule_4_due_at_more_than_30_days(self):
        due_at = (timezone.now() + timedelta(days=31)).isoformat()
        payload = {
            "asset_tag": "CAM-001",
            "employee_code": "EMP001",
            "due_at": due_at
        }
        response = self.client.post(self.checkout_url, payload, **self.auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "30 days" in response.json()["detail"].lower()

    def test_rule_8_unknown_asset_tag(self):
        due_at = (timezone.now() + timedelta(days=5)).isoformat()
        payload = {
            "asset_tag": "UNKNOWN-TAG",
            "employee_code": "EMP001",
            "due_at": due_at
        }
        response = self.client.post(self.checkout_url, payload, **self.auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_rule_8_unknown_employee_code(self):
        due_at = (timezone.now() + timedelta(days=5)).isoformat()
        payload = {
            "asset_tag": "CAM-001",
            "employee_code": "UNKNOWN-EMP",
            "due_at": due_at
        }
        response = self.client.post(self.checkout_url, payload, **self.auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_checkout_denied(self):
        due_at = (timezone.now() + timedelta(days=5)).isoformat()
        payload = {
            "asset_tag": "CAM-001",
            "employee_code": "EMP001",
            "due_at": due_at
        }
        response = self.client.post(self.checkout_url, payload)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
