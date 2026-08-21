from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from .views import HealthCheckView, AssetViewSet

app_name = 'assets'

router = DefaultRouter()
router.register(r'assets', AssetViewSet, basename='asset')

urlpatterns = [
    # Health check
    path('health/', HealthCheckView.as_view(), name='health-check'),

    # Authentication token endpoint
    path('auth/token/', obtain_auth_token, name='api-token-auth'),

    # ViewSets
    path('', include(router.urls)),
]
