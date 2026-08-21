from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from assets.views import HealthCheckView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', HealthCheckView.as_view(), name='root-health-check'),
    path('api/v1/', include('assets.urls')),

    # OpenAPI Schema & Interactive Docs (FastAPI-like Swagger UI & ReDoc)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='api-v1-swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
