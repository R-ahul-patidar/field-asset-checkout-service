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
class TestReturnAPI:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="returnuser",
            password="returnpassword123"
        )
        self.token = Token.objects.create(user=self.user)
        self.auth_headers = {'HTTP_AUTHORIZATION': f'Token {self.token.key}'}

        self.employee = Employee.objects.create(
            employee_code="EMP-RET-01",
            full_name="Bob Miller",
            email="bob.miller@example.com",
            is_active=True
        )
        self.asset = Asset.objects.create(
            asset_tag="CAM-RET-01",
            name="Panasonic Lumix",
            category=Asset.Category.CAMERA,
            status=Asset.Status.CHECKED_OUT,
            purchase_date=date(2024, 1, 15)
        )
        self.checkout = CheckOut.objects.create(
            asset=self.asset,
            employee=self.employee,
            due_at=timezone.now() + timedelta(days=5)
        )
        self.return_url = reverse('assets:checkout-return-asset', kwargs={'pk': self.checkout.id})

    def test_return_asset_normal_success(self):
        payload = {
            "condition_note": "Returned in perfect condition",
            "needs_maintenance": False
        }
        response = self.client.post(self.return_url, payload, **self.auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["returned_at"] is not None
        assert data["condition_note"] == "Returned in perfect condition"

        # Verify DB states
        self.checkout.refresh_from_db()
        assert self.checkout.returned_at is not None
        self.asset.refresh_from_db()
        assert self.asset.status == Asset.Status.AVAILABLE

    def test_return_asset_needs_maintenance(self):
        payload = {
            "condition_note": "Lens focus ring is loose, needs calibration",
            "needs_maintenance": True
        }
        response = self.client.post(self.return_url, payload, **self.auth_headers)
        assert response.status_code == status.HTTP_200_OK

        self.checkout.refresh_from_db()
        assert self.checkout.returned_at is not None
        self.asset.refresh_from_db()
        assert self.asset.status == Asset.Status.MAINTENANCE

    def test_return_already_returned_conflict(self):
        # First return succeeds
        response1 = self.client.post(
            self.return_url,
            {"condition_note": "Initial return", "needs_maintenance": False},
            **self.auth_headers
        )
        assert response1.status_code == status.HTTP_200_OK

        # Second return on already returned checkout must return 409 Conflict
        response2 = self.client.post(
            self.return_url,
            {"condition_note": "Second return attempt", "needs_maintenance": False},
            **self.auth_headers
        )
        assert response2.status_code == status.HTTP_409_CONFLICT
        assert "already been returned" in response2.json()["detail"].lower()

    def test_return_nonexistent_checkout_not_found(self):
        bad_url = reverse('assets:checkout-return-asset', kwargs={'pk': 999999})
        response = self.client.post(
            bad_url,
            {"condition_note": "Test", "needs_maintenance": False},
            **self.auth_headers
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_return_unauthenticated_denied(self):
        response = self.client.post(
            self.return_url,
            {"condition_note": "Unauthenticated test", "needs_maintenance": False}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
