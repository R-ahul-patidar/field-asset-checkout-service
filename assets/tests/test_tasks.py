import pytest
from datetime import date, timedelta
from django.utils import timezone

from assets.models import Asset, Employee, CheckOut, OverdueNotice
from assets.tasks import flag_overdue_checkouts


@pytest.mark.django_db
class TestOverdueTasks:
    def setup_method(self):
        self.employee = Employee.objects.create(
            employee_code="EMP-TSK-1",
            full_name="Task Tester",
            email="tasktester@example.com",
            is_active=True
        )
        now = timezone.now()

        # Asset & Checkout 1: Overdue (due 3 days ago, not returned)
        self.a1 = Asset.objects.create(
            asset_tag="TSK-A1", name="Overdue Asset 1", category=Asset.Category.LAPTOP,
            purchase_date=date(2024, 1, 1), status=Asset.Status.CHECKED_OUT
        )
        self.c1 = CheckOut.objects.create(
            asset=self.a1, employee=self.employee,
            due_at=now - timedelta(days=3),
            returned_at=None
        )
        CheckOut.objects.filter(id=self.c1.id).update(checked_out_at=now - timedelta(days=8))

        # Asset & Checkout 2: Overdue (due 1 day ago, not returned)
        self.a2 = Asset.objects.create(
            asset_tag="TSK-A2", name="Overdue Asset 2", category=Asset.Category.CAMERA,
            purchase_date=date(2024, 1, 1), status=Asset.Status.CHECKED_OUT
        )
        self.c2 = CheckOut.objects.create(
            asset=self.a2, employee=self.employee,
            due_at=now - timedelta(days=1),
            returned_at=None
        )
        CheckOut.objects.filter(id=self.c2.id).update(checked_out_at=now - timedelta(days=5))

        # Asset & Checkout 3: NOT overdue (due 4 days in future)
        self.a3 = Asset.objects.create(
            asset_tag="TSK-A3", name="Future Asset", category=Asset.Category.SENSOR,
            purchase_date=date(2024, 1, 1), status=Asset.Status.CHECKED_OUT
        )
        self.c3 = CheckOut.objects.create(
            asset=self.a3, employee=self.employee,
            due_at=now + timedelta(days=4),
            returned_at=None
        )

        # Asset & Checkout 4: Was overdue but already returned
        self.a4 = Asset.objects.create(
            asset_tag="TSK-A4", name="Returned Asset", category=Asset.Category.VEHICLE,
            purchase_date=date(2024, 1, 1), status=Asset.Status.AVAILABLE
        )
        self.c4 = CheckOut.objects.create(
            asset=self.a4, employee=self.employee,
            due_at=now - timedelta(days=5),
            returned_at=now - timedelta(days=1)
        )

    def test_flag_overdue_checkouts_creates_notices(self):
        # Initial state: 0 notices
        assert OverdueNotice.objects.count() == 0

        # First run: should create exactly 2 notices (for c1 and c2)
        result = flag_overdue_checkouts()
        assert result["notices_created"] == 2
        assert result["notices_skipped"] == 0
        assert OverdueNotice.objects.count() == 2

        today = timezone.localdate()
        assert OverdueNotice.objects.filter(checkout=self.c1, notice_date=today).exists()
        assert OverdueNotice.objects.filter(checkout=self.c2, notice_date=today).exists()
        assert not OverdueNotice.objects.filter(checkout=self.c3).exists()
        assert not OverdueNotice.objects.filter(checkout=self.c4).exists()

    def test_flag_overdue_checkouts_idempotent_multiple_runs(self):
        # Run 1: creates 2 notices
        res1 = flag_overdue_checkouts()
        assert res1["notices_created"] == 2
        assert OverdueNotice.objects.count() == 2

        # Run 2 on same day: creates 0 notices, skips 2
        res2 = flag_overdue_checkouts()
        assert res2["notices_created"] == 0
        assert res2["notices_skipped"] == 2
        assert OverdueNotice.objects.count() == 2

        # Run 3 on same day: still strictly 2 notices in database
        res3 = flag_overdue_checkouts()
        assert res3["notices_created"] == 0
        assert res3["notices_skipped"] == 2
        assert OverdueNotice.objects.count() == 2
