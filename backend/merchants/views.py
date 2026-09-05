"""
API views for Merchant and MerchantPolicy.

Merchant endpoints:
    GET  /api/merchants/        — list all merchants
    POST /api/merchants/        — create a merchant
    GET  /api/merchants/<id>/   — retrieve full merchant detail
                                  (includes embedded policy + product count)

Policy endpoints:
    GET        /api/policies/<merchant_id>/  — retrieve policy for a merchant
    PUT/PATCH  /api/policies/<merchant_id>/  — update policy for a merchant
"""

from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Merchant, MerchantPolicy
from .serializers import (
    MerchantSerializer,
    MerchantDetailSerializer,
    MerchantPolicySerializer,
)


# ---------------------------------------------------------------------------
# Merchant views
# ---------------------------------------------------------------------------


class MerchantListCreateView(APIView):
    """GET /api/merchants/  —  POST /api/merchants/"""

    def get(self, request):
        merchants = Merchant.objects.all()
        serializer = MerchantSerializer(merchants, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = MerchantSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MerchantDetailView(APIView):
    """
    GET /api/merchants/<id>/

    Returns full merchant detail including:
      - merchant fields
      - embedded policy (null if not yet configured)
      - product_count (annotated — no extra query)
    """

    def get(self, request, pk):
        merchant = get_object_or_404(
            Merchant.objects.select_related("policy").annotate(
                product_count=Count("products")
            ),
            pk=pk,
        )
        serializer = MerchantDetailSerializer(merchant)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# MerchantPolicy views
# ---------------------------------------------------------------------------


class MerchantPolicyView(APIView):
    """
    GET        /api/policies/<merchant_id>/
    PUT/PATCH  /api/policies/<merchant_id>/

    Policy is auto-created with sensible defaults when a merchant exists
    but has no policy record yet (avoids a two-step bootstrap flow).
    """

    _DEFAULTS = {
        "minimum_margin_percent": "0.00",
        "maximum_discount_percent": "0.00",
        "maximum_negotiation_rounds": 1,
        "auto_approval_limit": "0.00",
    }

    def _get_merchant(self, merchant_id):
        return get_object_or_404(Merchant, pk=merchant_id)

    def _get_policy(self, merchant):
        policy, _ = MerchantPolicy.objects.get_or_create(
            merchant=merchant, defaults=self._DEFAULTS
        )
        return policy

    def get(self, request, merchant_id):
        merchant = self._get_merchant(merchant_id)
        policy = self._get_policy(merchant)
        serializer = MerchantPolicySerializer(policy)
        return Response(serializer.data)

    def put(self, request, merchant_id):
        merchant = self._get_merchant(merchant_id)
        policy = self._get_policy(merchant)
        serializer = MerchantPolicySerializer(policy, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, merchant_id):
        merchant = self._get_merchant(merchant_id)
        policy = self._get_policy(merchant)
        serializer = MerchantPolicySerializer(policy, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
