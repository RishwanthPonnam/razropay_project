"""
Root URL configuration for Merchant OS AI.

All API routes are prefixed with /api/.
Individual app routes will be added here via include() as apps grow.
"""

from django.contrib import admin
from django.urls import include, path

from config.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),

    # -----------------------------------------------------------------
    # Health check — no authentication required
    # -----------------------------------------------------------------
    path("api/health/", health_check, name="health-check"),

    # -----------------------------------------------------------------
    # App API routes
    # -----------------------------------------------------------------
    path("api/", include("merchants.urls")),
    path("api/", include("products.urls")),
    path("api/", include("ai.urls")),
    path("api/", include("payments.urls")),
]

