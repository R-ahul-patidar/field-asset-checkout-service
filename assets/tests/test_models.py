import pytest
from datetime import date, timedelta
from django.utils import timezone
from django.db import IntegrityError, models
from django.db.models.deletion import ProtectedError

from assets.models import Asset, Employee, CheckOut, OverdueNotice


@pytest.mark.django_db
class TestAssetModel:
    def test_create_asset_default_status(self):
        asset = Asset.objects.create(
            asset_tag="CAM-001",
            name="Sony FX3 Cinema Camera",
            category=Asset.Category.CAMERA,
            purchase_date=date(2024, 1, 15)
        )
        assert asset.id is not None
        assert asset.status == Asset.Status.AVAILABLE
        assert str(asset) == "Sony FX3 Cinema Camera (CAM-001)"
        assert asset.created_at is not None
        assert asset.updated_at is not None

    def test_asset_tag_unique_constraint(self):
        Asset.objects.create(
            asset_tag="CAM-001",
            name="Camera 1",
            category=Asset.Category.CAMERA,
            purchase_date=date(2024, 1, 15)
        )
        with pytest.raises(IntegrityError):
            Asset.objects.create(
                asset_tag="CAM-001",
                name="Camera 2",
                category=Asset.Category.CAMERA,
                purchase_date=date(2024, 1, 16)
            )


@pytest.mark.django_db
class TestEmployeeModel:
    def test_create_employee_default_active(self):
        emp = Employee.objects.create(
            employee_code="EMP001",
            full_name="Alice Walker",
            email="alice@example.com"
        )
        assert emp.id is not None
        assert emp.is_active is True
        assert str(emp) == "Alice Walker (EMP001)"

    def test_employee_code_unique_constraint(self):
        Employee.objects.create(
            employee_code="EMP001",
            full_name="Alice Walker",
            email="alice@example.com"
        )
        with pytest.raises(IntegrityError):
            Employee.objects.create(
                employee_code="EMP001",
                full_name="Alice Duplicate",
                email="alice2@example.com"
            )

    def test_employee_email_unique_constraint(self):
        Employee.objects.create(
            employee_code="EMP001",
            full_name="Alice Walker",
            email="alice@example.com"
        )
        with pytest.raises(IntegrityError):
            Employee.objects.create(
                employee_code="EMP002",
                full_name="Bob Brown",
                email="alice@example.com"
            )


@pytest.mark.django_db
class TestCheckOutModel:
    def test_create_checkout(self):
        asset = Asset.objects.create(
            asset_tag="LAP-001",
            name="MacBook Pro 16",
            category=Asset.Category.LAPTOP,
            purchase_date=date(2024, 2, 1)
        )
        emp = Employee.objects.create(
            employee_code="EMP002",
            full_name="Bob Smith",
            email="bob@example.com"
        )
        due_at = timezone.now() + timedelta(days=7)
        checkout = CheckOut.objects.create(
            asset=asset,
            employee=emp,
            due_at=due_at
        )
        assert checkout.id is not None
        assert checkout.returned_at is None
        assert checkout.condition_note == ""
        assert checkout.asset == asset
        assert checkout.employee == emp
        assert "LAP-001" in str(checkout)

    def test_checkout_protect_deletion(self):
        asset = Asset.objects.create(
            asset_tag="SEN-001",
            name="Thermal Sensor Pro",
            category=Asset.Category.SENSOR,
            purchase_date=date(2024, 3, 1)
        )
        emp = Employee.objects.create(
            employee_code="EMP003",
            full_name="Charlie Davis",
            email="charlie@example.com"
        )
        CheckOut.objects.create(
            asset=asset,
            employee=emp,
            due_at=timezone.now() + timedelta(days=3)
        )

        with pytest.raises(ProtectedError):
            asset.delete()

        with pytest.raises(ProtectedError):
            emp.delete()


@pytest.mark.django_db
class TestOverdueNoticeModel:
    def test_create_and_unique_constraint(self):
        asset = Asset.objects.create(
            asset_tag="VEH-001",
            name="Field Drone Rover",
            category=Asset.Category.VEHICLE,
            purchase_date=date(2024, 1, 10)
        )
        emp = Employee.objects.create(
            employee_code="EMP004",
            full_name="Diana Prince",
            email="diana@example.com"
        )
        checkout = CheckOut.objects.create(
            asset=asset,
            employee=emp,
            due_at=timezone.now() - timedelta(days=2)
        )
        notice_date = timezone.now().date()
        notice = OverdueNotice.objects.create(
            checkout=checkout,
            notice_date=notice_date
        )
        assert notice.id is not None
        assert notice.created_at is not None

        # Duplicate notice on same checkout and notice_date should violate unique constraint
        with pytest.raises(IntegrityError):
            OverdueNotice.objects.create(
                checkout=checkout,
                notice_date=notice_date
            )

    def test_cascade_delete_checkout(self):
        asset = Asset.objects.create(
            asset_tag="VEH-002",
            name="Survey Drone",
            category=Asset.Category.VEHICLE,
            purchase_date=date(2024, 1, 10)
        )
        emp = Employee.objects.create(
            employee_code="EMP005",
            full_name="Evan Wright",
            email="evan@example.com"
        )
        checkout = CheckOut.objects.create(
            asset=asset,
            employee=emp,
            due_at=timezone.now() - timedelta(days=1)
        )
        OverdueNotice.objects.create(
            checkout=checkout,
            notice_date=timezone.now().date()
        )
        assert OverdueNotice.objects.count() == 1
        checkout.delete()
        assert OverdueNotice.objects.count() == 0
