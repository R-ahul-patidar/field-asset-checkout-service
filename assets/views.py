import logging
from django.db import connection
from django.db.models import Prefetch
from rest_framework import viewsets, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import Asset, Employee, CheckOut, OverdueNotice
from .serializers import AssetSerializer

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
