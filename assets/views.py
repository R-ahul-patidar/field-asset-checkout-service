import logging
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

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
