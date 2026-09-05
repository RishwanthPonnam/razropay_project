"""
URL patterns for the merchants app.
Mounted at /api/ by the root URLconf.
"""

from django.urls import path

from .views import MerchantListCreateView, MerchantDetailView, MerchantPolicyView

urlpatterns = [
    path("merchants/", MerchantListCreateView.as_view(), name="merchant-list-create"),
    path("merchants/<int:pk>/", MerchantDetailView.as_view(), name="merchant-detail"),
    path("policies/<int:merchant_id>/", MerchantPolicyView.as_view(), name="merchant-policy"),
]
