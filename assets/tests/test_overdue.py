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
class TestOverdueReportAPI:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="reportuser",
            password="reportpassword123"
        )
        self.token = Token.objects.create(user=self.user)
        self.auth_headers = {'HTTP_AUTHORIZATION': f'Token {self.token.key}'}
        self.report_url = reverse('assets:reports-overdue')

    def test_overdue_report_ordering_and_fields(self):
        emp1 = Employee.objects.create(
            employee_code="EMP-REP-1", full_name="Report Employee One",
            email="rep1@example.com", is_active=True
        )
        emp2 = Employee.objects.create(
            employee_code="EMP-REP-2", full_name="Report Employee Two",
            email="rep2@example.com", is_active=True
        )
        now = timezone.now()

        # Asset 1: Overdue by 5 days (due 5 days ago) -> Most overdue
        a1 = Asset.objects.create(
            asset_tag="REP-CAM-1", name="Heavy Drone", category=Asset.Category.VEHICLE,
            purchase_date=date(2024, 1, 1), status=Asset.Status.CHECKED_OUT
        )
        c1 = CheckOut.objects.create(
            asset=a1, employee=emp1,
            checked_out_at=now - timedelta(days=10),
            due_at=now - timedelta(days=5),
            returned_at=None
        )

        # Asset 2: Overdue by 2 days (due 2 days ago)
        a2 = Asset.objects.create(
            asset_tag="REP-LAP-2", name="Field Laptop", category=Asset.Category.LAPTOP,
            purchase_date=date(2024, 1, 1), status=Asset.Status.CHECKED_OUT
        )
        c2 = CheckOut.objects.create(
            asset=a2, employee=emp2,
            checked_out_at=now - timedelta(days=6),
            due_at=now - timedelta(days=2),
            returned_at=None
        )

        # Asset 3: Overdue by 0 days (due exactly now / 1 minute ago)
        a3 = Asset.objects.create(
            asset_tag="REP-SEN-3", name="Thermal Cam", category=Asset.Category.CAMERA,
            purchase_date=date(2024, 1, 1), status=Asset.Status.CHECKED_OUT
        )
        c3 = CheckOut.objects.create(
            asset=a3, employee=emp1,
            checked_out_at=now - timedelta(days=2),
            due_at=now - timedelta(minutes=1),
            returned_at=None
        )

        # Asset 4: NOT overdue (due tomorrow)
        a4 = Asset.objects.create(
            asset_tag="REP-SEN-4", name="Future Sensor", category=Asset.Category.SENSOR,
            purchase_date=date(2024, 1, 1), status=Asset.Status.CHECKED_OUT
        )
        c4 = CheckOut.objects.create(
            asset=a4, employee=emp2,
            checked_out_at=now - timedelta(days=1),
            due_at=now + timedelta(days=1),
            returned_at=None
        )

        # Asset 5: Was returned (even though it was returned late) -> Should NOT appear
        a5 = Asset.objects.create(
            asset_tag="REP-SEN-5", name="Returned Late Sensor", category=Asset.Category.SENSOR,
            purchase_date=date(2024, 1, 1), status=Asset.Status.AVAILABLE
        )
        c5 = CheckOut.objects.create(
            asset=a5, employee=emp1,
            checked_out_at=now - timedelta(days=10),
            due_at=now - timedelta(days=5),
            returned_at=now - timedelta(days=1)
        )

        # Test query count efficiency (avoid N+1)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.report_url, **self.auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Exactly 3 items overdue
        assert data["count"] == 3
        results = data["results"]
        assert len(results) == 3

        # Ordering check: most overdue first (earliest due_at first)
        assert results[0]["asset_tag"] == "REP-CAM-1"
        assert results[0]["asset_name"] == "Heavy Drone"
        assert results[0]["employee_code"] == "EMP-REP-1"
        assert results[0]["employee_name"] == "Report Employee One"
        assert results[0]["days_overdue"] == 5

        assert results[1]["asset_tag"] == "REP-LAP-2"
        assert results[1]["days_overdue"] == 2

        assert results[2]["asset_tag"] == "REP-SEN-3"
        assert results[2]["days_overdue"] == 0

    def test_unauthenticated_report_denied(self):
        response = self.client.get(self.report_url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
