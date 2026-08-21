from django.contrib import admin
from .models import Asset, Employee, CheckOut, OverdueNotice


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('asset_tag', 'name', 'category', 'status', 'purchase_date', 'created_at')
    list_filter = ('status', 'category', 'purchase_date')
    search_fields = ('asset_tag', 'name')
    ordering = ('-created_at',)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_code', 'full_name', 'email', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('employee_code', 'full_name', 'email')
    ordering = ('employee_code',)


@admin.register(CheckOut)
class CheckOutAdmin(admin.ModelAdmin):
    list_display = ('id', 'asset', 'employee', 'checked_out_at', 'due_at', 'returned_at')
    list_filter = ('returned_at', 'due_at', 'checked_out_at')
    search_fields = ('asset__asset_tag', 'employee__employee_code', 'employee__full_name')
    ordering = ('-checked_out_at',)


@admin.register(OverdueNotice)
class OverdueNoticeAdmin(admin.ModelAdmin):
    list_display = ('id', 'checkout', 'notice_date', 'created_at')
    list_filter = ('notice_date',)
    search_fields = ('checkout__asset__asset_tag', 'checkout__employee__employee_code')
    ordering = ('-created_at',)
