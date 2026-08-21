from django.db import models


class Asset(models.Model):
    """
    Represents physical equipment available for check-out by employees.
    """
    class Category(models.TextChoices):
        CAMERA = 'CAMERA', 'Camera'
        LAPTOP = 'LAPTOP', 'Laptop'
        SENSOR = 'SENSOR', 'Sensor'
        VEHICLE = 'VEHICLE', 'Vehicle'

    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        CHECKED_OUT = 'CHECKED_OUT', 'Checked Out'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance'

    asset_tag = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=Category.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
        db_index=True
    )
    purchase_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'category']),
        ]

    def __str__(self):
        return f"{self.name} ({self.asset_tag})"


class Employee(models.Model):
    """
    Represents an internal employee authorized to check out assets.
    """
    employee_code = models.CharField(max_length=16, unique=True, db_index=True)
    full_name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['employee_code']

    def __str__(self):
        return f"{self.full_name} ({self.employee_code})"


class CheckOut(models.Model):
    """
    Represents a check-out transaction of an asset by an employee.
    """
    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name='checkouts'
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='checkouts'
    )
    checked_out_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField()
    returned_at = models.DateTimeField(null=True, blank=True)
    condition_note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-checked_out_at']
        indexes = [
            models.Index(fields=['returned_at']),
            models.Index(fields=['due_at']),
            models.Index(fields=['checked_out_at']),
            models.Index(fields=['employee', 'returned_at']),
        ]

    def __str__(self):
        return f"CheckOut #{self.id}: {self.asset.asset_tag} -> {self.employee.employee_code}"


class OverdueNotice(models.Model):
    """
    Records overdue notices sent or generated for open checkouts past due date.
    """
    checkout = models.ForeignKey(
        CheckOut,
        on_delete=models.CASCADE,
        related_name='notices'
    )
    notice_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['checkout', 'notice_date'],
                name='unique_checkout_notice_date'
            )
        ]

    def __str__(self):
        return f"Notice for CheckOut #{self.checkout_id} on {self.notice_date}"
