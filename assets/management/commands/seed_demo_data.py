from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token

from assets.models import Asset, Employee, CheckOut, OverdueNotice


class Command(BaseCommand):
    help = "Seeds the database with representative demo data (assets, employees, checkouts, notices, and demo user)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding field asset checkout service demo data..."))

        # 1. Evaluator Admin User & Token
        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@artikate.local", "is_staff": True, "is_superuser": True}
        )
        admin_user.set_password("adminpassword123")
        admin_user.save()

        token, _ = Token.objects.get_or_create(user=admin_user)
        self.stdout.write(self.style.SUCCESS(f"Demo User: 'admin' | Password: 'adminpassword123' | Token: {token.key}"))

        # 2. Employees (5 total, 1 inactive)
        employees_data = [
            {"code": "EMP-001", "name": "Sarah Connor", "email": "sarah.connor@example.com", "active": True},
            {"code": "EMP-002", "name": "John Doe", "email": "john.doe@example.com", "active": True},
            {"code": "EMP-003", "name": "Jane Smith", "email": "jane.smith@example.com", "active": True},
            {"code": "EMP-004", "name": "Robert Vance", "email": "robert.vance@example.com", "active": True},
            {"code": "EMP-005", "name": "Inactive Jones", "email": "inactive.jones@example.com", "active": False},
        ]
        employees = {}
        for ed in employees_data:
            emp, _ = Employee.objects.update_or_create(
                employee_code=ed["code"],
                defaults={
                    "full_name": ed["name"],
                    "email": ed["email"],
                    "is_active": ed["active"]
                }
            )
            employees[ed["code"]] = emp
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(employees)} employees (including 1 inactive)."))

        # 3. Assets (10 total across all 4 categories)
        assets_data = [
            {"tag": "LAP-001", "name": "ThinkPad X1 Carbon Gen 11", "category": Asset.Category.LAPTOP, "status": Asset.Status.CHECKED_OUT, "purchase": date(2023, 5, 10)},
            {"tag": "LAP-002", "name": "MacBook Pro 16 M3 Max", "category": Asset.Category.LAPTOP, "status": Asset.Status.AVAILABLE, "purchase": date(2023, 11, 20)},
            {"tag": "LAP-003", "name": "Dell XPS 15 Field Unit", "category": Asset.Category.LAPTOP, "status": Asset.Status.AVAILABLE, "purchase": date(2024, 1, 15)},
            {"tag": "CAM-001", "name": "Sony Alpha A7 IV Full-Frame", "category": Asset.Category.CAMERA, "status": Asset.Status.CHECKED_OUT, "purchase": date(2023, 3, 12)},
            {"tag": "CAM-002", "name": "Canon EOS R5 Field Rig", "category": Asset.Category.CAMERA, "status": Asset.Status.AVAILABLE, "purchase": date(2023, 8, 5)},
            {"tag": "CAM-003", "name": "DJI Mavic 3 Enterprise Thermal Drone", "category": Asset.Category.CAMERA, "status": Asset.Status.AVAILABLE, "purchase": date(2024, 2, 18)},
            {"tag": "SEN-001", "name": "FLIR T860 High-Res Thermal Camera", "category": Asset.Category.SENSOR, "status": Asset.Status.CHECKED_OUT, "purchase": date(2023, 9, 1)},
            {"tag": "SEN-002", "name": "Bosch Geo-LiDAR Spatial Scanner", "category": Asset.Category.SENSOR, "status": Asset.Status.MAINTENANCE, "purchase": date(2022, 12, 14)},
            {"tag": "VEH-001", "name": "Toyota Hilux 4x4 Heavy Utility", "category": Asset.Category.VEHICLE, "status": Asset.Status.CHECKED_OUT, "purchase": date(2021, 6, 30)},
            {"tag": "VEH-002", "name": "Ford Ranger Field Truck Double Cab", "category": Asset.Category.VEHICLE, "status": Asset.Status.AVAILABLE, "purchase": date(2022, 4, 10)},
        ]
        assets = {}
        for ad in assets_data:
            ast, _ = Asset.objects.update_or_create(
                asset_tag=ad["tag"],
                defaults={
                    "name": ad["name"],
                    "category": ad["category"],
                    "status": ad["status"],
                    "purchase_date": ad["purchase"]
                }
            )
            assets[ad["tag"]] = ast
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(assets)} assets across all 4 categories."))

        # 4. CheckOut Transactions (Controlled timestamps and states)
        now = timezone.now()

        # Clean existing seeded checkouts to ensure idempotency and accurate relative dates
        CheckOut.objects.filter(asset__asset_tag__in=assets.keys()).delete()

        # 1. Overdue checkout #1: LAP-001 -> Sarah Connor (due 4 days ago)
        c1 = CheckOut.objects.create(
            asset=assets["LAP-001"],
            employee=employees["EMP-001"],
            due_at=now - timedelta(days=4),
            returned_at=None
        )
        CheckOut.objects.filter(id=c1.id).update(checked_out_at=now - timedelta(days=12))

        # 2. Overdue checkout #2: CAM-001 -> John Doe (due 8 days ago)
        c2 = CheckOut.objects.create(
            asset=assets["CAM-001"],
            employee=employees["EMP-002"],
            due_at=now - timedelta(days=8),
            returned_at=None
        )
        CheckOut.objects.filter(id=c2.id).update(checked_out_at=now - timedelta(days=18))

        # 3. Open not overdue #1: SEN-001 -> Sarah Connor (due 12 days ahead)
        c3 = CheckOut.objects.create(
            asset=assets["SEN-001"],
            employee=employees["EMP-001"],
            due_at=now + timedelta(days=12),
            returned_at=None
        )
        CheckOut.objects.filter(id=c3.id).update(checked_out_at=now - timedelta(days=2))

        # 4. Open not overdue #2: VEH-001 -> Jane Smith (due 6 days ahead)
        c4 = CheckOut.objects.create(
            asset=assets["VEH-001"],
            employee=employees["EMP-003"],
            due_at=now + timedelta(days=6),
            returned_at=None
        )
        CheckOut.objects.filter(id=c4.id).update(checked_out_at=now - timedelta(days=1))

        # 5. Returned on time #1: LAP-002 -> John Doe (hold duration: 8 days)
        c5 = CheckOut.objects.create(
            asset=assets["LAP-002"],
            employee=employees["EMP-002"],
            due_at=now - timedelta(days=10),
            returned_at=now - timedelta(days=12),
            condition_note="Returned in excellent condition"
        )
        CheckOut.objects.filter(id=c5.id).update(checked_out_at=now - timedelta(days=20))

        # 6. Returned on time #2: CAM-002 -> Jane Smith (hold duration: 9 days)
        c6 = CheckOut.objects.create(
            asset=assets["CAM-002"],
            employee=employees["EMP-003"],
            due_at=now - timedelta(days=5),
            returned_at=now - timedelta(days=6),
            condition_note="Clean optics and fresh sensor pack"
        )
        CheckOut.objects.filter(id=c6.id).update(checked_out_at=now - timedelta(days=15))

        # 7. Returned late: SEN-002 -> Robert Vance (due 15 days ago, returned 10 days ago, hold duration: 15 days)
        c7 = CheckOut.objects.create(
            asset=assets["SEN-002"],
            employee=employees["EMP-004"],
            due_at=now - timedelta(days=15),
            returned_at=now - timedelta(days=10),
            condition_note="LiDAR mirror calibration drift detected. Sent to maintenance."
        )
        CheckOut.objects.filter(id=c7.id).update(checked_out_at=now - timedelta(days=25))

        # 5. Overdue Notices (Idempotent seed notices for overdue items)
        today = timezone.localdate()
        for co in [c1, c2]:
            OverdueNotice.objects.get_or_create(
                checkout=co,
                notice_date=today
            )

        self.stdout.write(self.style.SUCCESS("Seeded 7 checkouts (2 currently overdue, 2 open on time, 2 returned on time, 1 returned late)."))
        self.stdout.write(self.style.SUCCESS("Database demo seeding completed successfully!"))
