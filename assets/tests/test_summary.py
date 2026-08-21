import pytest
from datetime import date, timedelta
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token

from assets.models import Asset, Employee, CheckOut


@pytest.mark.django_db
class TestEmployeeSummaryAPI:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="summaryuser",
            password="summarypassword123"
        )
        self.token = Token.objects.create(user=self.user)
        self.auth_headers = {'HTTP_AUTHORIZATION': f'Token {self.token.key}'}

    def test_employee_summary_with_controlled_data(self):
        emp = Employee.objects.create(
            employee_code="EMP-SUM-01",
            full_name="Controlled Employee",
            email="controlled@example.com",
            is_active=True
        )
        now = timezone.now()

        # Item 1: Returned after 2 days (checked out 10 days ago, returned 8 days ago)
        a1 = Asset.objects.create(
            asset_tag="SUM-A1", name="Asset 1", category=Asset.Category.LAPTOP,
            purchase_date=date(2024, 1, 1), status=Asset.Status.AVAILABLE
        )
        c1 = CheckOut.objects.create(
            asset=a1, employee=emp,
            due_at=now - timedelta(days=5),
            returned_at=now - timedelta(days=8)
        )
        CheckOut.objects.filter(id=c1.id).update(checked_out_at=now - timedelta(days=10))

        # Item 2: Returned after 4 days (checked out 6 days ago, returned 2 days ago)
        a2 = Asset.objects.create(
            asset_tag="SUM-A2", name="Asset 2", category=Asset.Category.CAMERA,
            purchase_date=date(2024, 1, 1), status=Asset.Status.AVAILABLE
        )
        c2 = CheckOut.objects.create(
            asset=a2, employee=emp,
            due_at=now - timedelta(days=1),
            returned_at=now - timedelta(days=2)
        )
        CheckOut.objects.filter(id=c2.id).update(checked_out_at=now - timedelta(days=6))

        # Item 3: Currently held and overdue (due 2 days ago)
        a3 = Asset.objects.create(
            asset_tag="SUM-A3", name="Asset 3", category=Asset.Category.SENSOR,
            purchase_date=date(2024, 1, 1), status=Asset.Status.CHECKED_OUT
        )
        c3 = CheckOut.objects.create(
            asset=a3, employee=emp,
            due_at=now - timedelta(days=2),
            returned_at=None
        )
        CheckOut.objects.filter(id=c3.id).update(checked_out_at=now - timedelta(days=5))

        # Item 4: Currently held and NOT overdue (due 3 days from now)
        a4 = Asset.objects.create(
            asset_tag="SUM-A4", name="Asset 4", category=Asset.Category.VEHICLE,
            purchase_date=date(2024, 1, 1), status=Asset.Status.CHECKED_OUT
        )
        c4 = CheckOut.objects.create(
            asset=a4, employee=emp,
            due_at=now + timedelta(days=3),
            returned_at=None
        )
        CheckOut.objects.filter(id=c4.id).update(checked_out_at=now - timedelta(days=1))

        url = reverse('assets:employee-summary', kwargs={'employee_code': emp.employee_code})

        # Test single query execution
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url, **self.auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["lifetime_checkouts"] == 4
        assert data["currently_held"] == 2
        assert data["currently_overdue"] == 1
        # Mean of 2.0 and 4.0 days is 3.0 days
        assert data["mean_hold_duration_days"] == 3.0

    def test_employee_with_no_checkouts(self):
        emp = Employee.objects.create(
            employee_code="EMP-EMPTY",
            full_name="Empty Employee",
            email="empty@example.com",
            is_active=True
        )
        url = reverse('assets:employee-summary', kwargs={'employee_code': emp.employee_code})
        response = self.client.get(url, **self.auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["lifetime_checkouts"] == 0
        assert data["currently_held"] == 0
        assert data["currently_overdue"] == 0
        assert data["mean_hold_duration_days"] is None

    def test_nonexistent_employee_not_found(self):
        url = reverse('assets:employee-summary', kwargs={'employee_code': "NONEXISTENT"})
        response = self.client.get(url, **self.auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_summary_denied(self):
        url = reverse('assets:employee-summary', kwargs={'employee_code': "EMP-SUM-01"})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
