from rest_framework import serializers
from .models import Asset, Employee, CheckOut, OverdueNotice


class CurrentHolderSerializer(serializers.Serializer):
    employee_code = serializers.CharField()
    name = serializers.CharField()


class AssetSerializer(serializers.ModelSerializer):
    current_holder = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = [
            'id',
            'asset_tag',
            'name',
            'category',
            'status',
            'purchase_date',
            'created_at',
            'updated_at',
            'current_holder',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'current_holder']

    def get_current_holder(self, obj):
        if obj.status != Asset.Status.CHECKED_OUT:
            return None

        # Use prefetched active_checkouts if available to prevent N+1 queries
        if hasattr(obj, 'active_checkouts'):
            active = obj.active_checkouts
            if active:
                return {
                    "employee_code": active[0].employee.employee_code,
                    "name": active[0].employee.full_name,
                }
            return None

        active_checkout = (
            obj.checkouts
            .filter(returned_at__isnull=True)
            .select_related('employee')
            .first()
        )
        if active_checkout:
            return {
                "employee_code": active_checkout.employee.employee_code,
                "name": active_checkout.employee.full_name,
            }
        return None
