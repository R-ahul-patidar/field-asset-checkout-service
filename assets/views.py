import logging
from datetime import timedelta
from django.db import connection, transaction, OperationalError, IntegrityError
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import viewsets, filters, status, mixins
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import Asset, Employee, CheckOut, OverdueNotice
from .serializers import (
    AssetSerializer,
    CheckOutCreateSerializer,
    CheckOutReturnSerializer,
    CheckOutSerializer,
)

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """
    Unauthenticated health check endpoint reporting service and database connectivity.
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            connection.ensure_connection()
            return Response(
                {
                    "status": "healthy",
                    "database": "connected"
                },
                status=status.HTTP_200_OK
            )
        except Exception:
            logger.exception("Health check database connectivity failure")
            return Response(
                {
                    "status": "unhealthy",
                    "database": "disconnected"
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class AssetViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing and viewing field assets.
    Supports list, create, and retrieve with filtering and search.
    """
    http_method_names = ['get', 'post', 'head', 'options']
    serializer_class = AssetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'category']
    search_fields = ['name', 'asset_tag']
    ordering_fields = ['created_at', 'purchase_date', 'name', 'asset_tag', 'status', 'category']
    ordering = ['-created_at']

    def get_queryset(self):
        return Asset.objects.all().prefetch_related(
            Prefetch(
                'checkouts',
                queryset=CheckOut.objects.filter(returned_at__isnull=True).select_related('employee'),
                to_attr='active_checkouts'
            )
        )


class CheckOutViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet
):
    """
    API endpoint for asset check-out and return operations.
    Enforces business rules with strict database-level concurrency and atomic locking.
    """
    queryset = CheckOut.objects.all().select_related('asset', 'employee')
    serializer_class = CheckOutSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = CheckOutCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        asset_tag = serializer.validated_data['asset_tag']
        employee_code = serializer.validated_data['employee_code']
        due_at = serializer.validated_data['due_at']

        # Rule 4: due_at must be in the future and <= 30 days from now
        now = timezone.now()
        if due_at <= now:
            return Response(
                {"detail": "due_at must be in the future."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if due_at > now + timedelta(days=30):
            return Response(
                {"detail": "due_at cannot be more than 30 days in the future."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                # Consistent Lock Ordering: 1. Employee, 2. Asset (prevents deadlocks)
                # Rule 8: Unknown employee_code -> 404
                try:
                    employee = Employee.objects.select_for_update().get(employee_code=employee_code)
                except Employee.DoesNotExist:
                    return Response(
                        {"detail": f"Employee with code '{employee_code}' not found."},
                        status=status.HTTP_404_NOT_FOUND
                    )

                # Rule 2: Inactive employee cannot check out anything -> 400
                if not employee.is_active:
                    return Response(
                        {"detail": "Inactive employee cannot check out assets."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Rule 3: Max 3 open checkouts -> 409
                open_count = CheckOut.objects.filter(employee=employee, returned_at__isnull=True).count()
                if open_count >= 3:
                    return Response(
                        {"detail": "Employee has reached the maximum limit of 3 open check-outs."},
                        status=status.HTTP_409_CONFLICT
                    )

                # Rule 8: Unknown asset_tag -> 404
                try:
                    asset = Asset.objects.select_for_update().get(asset_tag=asset_tag)
                except Asset.DoesNotExist:
                    return Response(
                        {"detail": f"Asset with tag '{asset_tag}' not found."},
                        status=status.HTTP_404_NOT_FOUND
                    )

                # Rule 1: Asset status must be AVAILABLE -> 409
                if asset.status != Asset.Status.AVAILABLE:
                    return Response(
                        {"detail": f"Asset '{asset_tag}' is not available (current status: {asset.status})."},
                        status=status.HTTP_409_CONFLICT
                    )

                # Rule 5: Create checkout and set asset status to CHECKED_OUT atomically
                checkout = CheckOut.objects.create(
                    asset=asset,
                    employee=employee,
                    due_at=due_at
                )
                asset.status = Asset.Status.CHECKED_OUT
                asset.save(update_fields=['status', 'updated_at'])

                response_serializer = CheckOutSerializer(checkout)
                return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        except (OperationalError, IntegrityError) as exc:
            logger.warning("Concurrency conflict during checkout: %s", exc)
            return Response(
                {"detail": "Conflict occurred during checkout. Please retry."},
                status=status.HTTP_409_CONFLICT
            )

    @action(detail=True, methods=['post'], url_path='return')
    def return_asset(self, request, pk=None):
        """
        Rule 6: Return a checked-out asset.
        Sets returned_at to now, updates asset status to AVAILABLE (or MAINTENANCE),
        and prevents already-returned checkouts (409 Conflict).
        """
        serializer = CheckOutReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        condition_note = serializer.validated_data.get('condition_note', '')
        needs_maintenance = serializer.validated_data.get('needs_maintenance', False)

        try:
            with transaction.atomic():
                try:
                    checkout = (
                        CheckOut.objects
                        .select_for_update()
                        .select_related('asset')
                        .get(pk=pk)
                    )
                except CheckOut.DoesNotExist:
                    return Response(
                        {"detail": f"CheckOut #{pk} not found."},
                        status=status.HTTP_404_NOT_FOUND
                    )

                # Rule 6: Returning an already-returned check-out -> 409 Conflict
                if checkout.returned_at is not None:
                    return Response(
                        {"detail": f"CheckOut #{pk} has already been returned."},
                        status=status.HTTP_409_CONFLICT
                    )

                # Lock the asset row
                asset = Asset.objects.select_for_update().get(pk=checkout.asset_id)

                checkout.returned_at = timezone.now()
                if condition_note:
                    checkout.condition_note = condition_note
                checkout.save(update_fields=['returned_at', 'condition_note'])

                if needs_maintenance:
                    asset.status = Asset.Status.MAINTENANCE
                else:
                    asset.status = Asset.Status.AVAILABLE
                asset.save(update_fields=['status', 'updated_at'])

                response_serializer = CheckOutSerializer(checkout)
                return Response(response_serializer.data, status=status.HTTP_200_OK)
        except (OperationalError, IntegrityError) as exc:
            logger.warning("Concurrency conflict during return: %s", exc)
            return Response(
                {"detail": "Conflict occurred during return operation. Please retry."},
                status=status.HTTP_409_CONFLICT
            )
