from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token
from .views import HealthCheckView

app_name = 'assets'

urlpatterns = [
    # Health check
    path('health/', HealthCheckView.as_view(), name='health-check'),

    # Authentication token endpoint
    path('auth/token/', obtain_auth_token, name='api-token-auth'),
]
