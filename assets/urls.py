from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from .views import (
    HealthCheckView,
    AssetViewSet,
    CheckOutViewSet,
    EmployeeSummaryView,
    OverdueReportView,
)

app_name = 'assets'

router = DefaultRouter()
router.register(r'assets', AssetViewSet, basename='asset')
router.register(r'checkouts', CheckOutViewSet, basename='checkout')

urlpatterns = [
    # Health check
    path('health/', HealthCheckView.as_view(), name='health-check'),

    # Authentication token endpoint
    path('auth/token/', obtain_auth_token, name='api-token-auth'),

    # Employee Summary
    path('employees/<str:employee_code>/summary/', EmployeeSummaryView.as_view(), name='employee-summary'),

    # Overdue Report
    path('reports/overdue/', OverdueReportView.as_view(), name='reports-overdue'),

    # ViewSets
    path('', include(router.urls)),
]
