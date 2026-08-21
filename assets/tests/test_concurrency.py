import pytest
import concurrent.futures
from datetime import date, timedelta
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django.db import connection
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token

from assets.models import Asset, Employee, CheckOut


@pytest.mark.django_db(transaction=True)
class TestCheckOutConcurrency:
    def setup_method(self):
        self.user = User.objects.create_user(
            username="concurrentuser",
            password="concurrentpassword123"
        )
        self.token = Token.objects.create(user=self.user)
        self.checkout_url = reverse('assets:checkout-list')

    def _perform_checkout(self, asset_tag, employee_code, due_at):
        from django.db import connections
        client = APIClient()
        response = client.post(
            self.checkout_url,
            {
                "asset_tag": asset_tag,
                "employee_code": employee_code,
                "due_at": due_at,
            },
            HTTP_AUTHORIZATION=f'Token {self.token.key}'
        )
        status_code = response.status_code
        data = response.json()
        connections.close_all()
        return status_code, data

    def test_concurrent_checkouts_same_asset_single_winner(self):
        """
        Rule 7: If two check-out requests for the same asset arrive at the same moment,
        exactly one must succeed (201) and the other must receive 409 Conflict.
        """
        asset = Asset.objects.create(
            asset_tag="CONC-CAM-01",
            name="Concurrent Camera",
            category=Asset.Category.CAMERA,
            status=Asset.Status.AVAILABLE,
            purchase_date=date(2024, 1, 1)
        )
        emp1 = Employee.objects.create(
            employee_code="EMP-C1",
            full_name="Employee One",
            email="emp1@example.com",
            is_active=True
        )
        emp2 = Employee.objects.create(
            employee_code="EMP-C2",
            full_name="Employee Two",
            email="emp2@example.com",
            is_active=True
        )
        due_at = (timezone.now() + timedelta(days=5)).isoformat()

        # Run 2 concurrent checkout requests for the same asset
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(self._perform_checkout, asset.asset_tag, emp1.employee_code, due_at)
            future2 = executor.submit(self._perform_checkout, asset.asset_tag, emp2.employee_code, due_at)

            res1_code, _ = future1.result()
            res2_code, _ = future2.result()

        status_codes = [res1_code, res2_code]
        assert status.HTTP_201_CREATED in status_codes, f"Expected one 201, got {status_codes}"
        assert status.HTTP_409_CONFLICT in status_codes, f"Expected one 409, got {status_codes}"
        assert status_codes.count(status.HTTP_201_CREATED) == 1
        assert status_codes.count(status.HTTP_409_CONFLICT) == 1

        # Check DB state
        asset.refresh_from_db()
        assert asset.status == Asset.Status.CHECKED_OUT
        assert CheckOut.objects.filter(asset=asset, returned_at__isnull=True).count() == 1

    def test_concurrent_checkouts_employee_limit_race(self):
        """
        Rule 3 & 7: If an employee currently has 2 open checkouts and receives 2 simultaneous
        checkout requests for different assets, exactly one must succeed (reaching 3),
        and the other must fail with 409 Conflict.
        """
        emp = Employee.objects.create(
            employee_code="EMP-LIMIT",
            full_name="Limit Employee",
            email="limit@example.com",
            is_active=True
        )
        # Create 2 existing open checkouts
        for i in range(2):
            a = Asset.objects.create(
                asset_tag=f"PRE-SEN-{i}",
                name=f"Existing Asset {i}",
                category=Asset.Category.SENSOR,
                status=Asset.Status.CHECKED_OUT,
                purchase_date=date(2024, 1, 1)
            )
            CheckOut.objects.create(
                asset=a,
                employee=emp,
                due_at=timezone.now() + timedelta(days=3)
            )

        # 2 available candidate assets
        asset_a = Asset.objects.create(
            asset_tag="CAND-LAP-A",
            name="Laptop A",
            category=Asset.Category.LAPTOP,
            status=Asset.Status.AVAILABLE,
            purchase_date=date(2024, 1, 1)
        )
        asset_b = Asset.objects.create(
            asset_tag="CAND-LAP-B",
            name="Laptop B",
            category=Asset.Category.LAPTOP,
            status=Asset.Status.AVAILABLE,
            purchase_date=date(2024, 1, 1)
        )
        due_at = (timezone.now() + timedelta(days=5)).isoformat()

        # Run 2 concurrent checkout requests for the same employee
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(self._perform_checkout, asset_a.asset_tag, emp.employee_code, due_at)
            future_b = executor.submit(self._perform_checkout, asset_b.asset_tag, emp.employee_code, due_at)

            res_a_code, _ = future_a.result()
            res_b_code, _ = future_b.result()

        status_codes = [res_a_code, res_b_code]
        assert status.HTTP_201_CREATED in status_codes, f"Expected one 201, got {status_codes}"
        assert status.HTTP_409_CONFLICT in status_codes, f"Expected one 409, got {status_codes}"
        assert status_codes.count(status.HTTP_201_CREATED) == 1
        assert status_codes.count(status.HTTP_409_CONFLICT) == 1

        # Total open checkouts for employee must be exactly 3
        open_count = CheckOut.objects.filter(employee=emp, returned_at__isnull=True).count()
        assert open_count == 3
