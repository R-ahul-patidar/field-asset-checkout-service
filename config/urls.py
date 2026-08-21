from django.contrib import admin
from django.urls import path, include
from assets.views import HealthCheckView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', HealthCheckView.as_view(), name='root-health-check'),
    path('api/v1/', include('assets.urls')),
]
