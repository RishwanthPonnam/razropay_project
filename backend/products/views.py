"""
API views for Product.

    GET  /api/products/       — list all products (with optional filters)
    POST /api/products/       — create a product
    GET  /api/products/<id>/  — retrieve a single product

Supported query parameters for GET /api/products/:
    merchant_id   — filter by merchant PK
    category      — exact match (case-insensitive)
    search        — partial match on name or description
    min_price     — price >= value
    max_price     — price <= value
    is_active     — 'true' / 'false'
    in_stock      — 'true' returns only products with inventory_quantity > 0
                    'false' returns products with inventory_quantity == 0

Filters are combinable; all provided filters are applied together (AND logic).
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Product
from .serializers import ProductSerializer


def _parse_bool(value: str) -> bool | None:
    """Return True/False for recognised boolean strings, else None."""
    if value is None:
        return None
    if value.lower() in ("true", "1", "yes"):
        return True
    if value.lower() in ("false", "0", "no"):
        return False
    return None


class ProductListCreateView(APIView):
    """GET /api/products/  —  POST /api/products/"""

    def get(self, request):
        qs = Product.objects.select_related("merchant").all()

        # ----------------------------------------------------------------
        # merchant_id filter
        # ----------------------------------------------------------------
        merchant_id = request.query_params.get("merchant_id")
        if merchant_id is not None:
            qs = qs.filter(merchant_id=merchant_id)

        # ----------------------------------------------------------------
        # category filter (case-insensitive exact match)
        # ----------------------------------------------------------------
        category = request.query_params.get("category")
        if category:
            qs = qs.filter(category__iexact=category)

        # ----------------------------------------------------------------
        # search filter — partial match on name or description
        # ----------------------------------------------------------------
        search = request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(
                description__icontains=search
            )
            # Re-apply select_related after the union to keep the optimisation
            qs = Product.objects.select_related("merchant").filter(
                pk__in=qs.values_list("pk", flat=True)
            )

        # ----------------------------------------------------------------
        # price range filters
        # ----------------------------------------------------------------
        min_price = request.query_params.get("min_price")
        if min_price is not None:
            qs = qs.filter(price__gte=min_price)

        max_price = request.query_params.get("max_price")
        if max_price is not None:
            qs = qs.filter(price__lte=max_price)

        # ----------------------------------------------------------------
        # is_active filter
        # ----------------------------------------------------------------
        is_active_raw = request.query_params.get("is_active")
        is_active = _parse_bool(is_active_raw)
        if is_active is not None:
            qs = qs.filter(is_active=is_active)

        # ----------------------------------------------------------------
        # in_stock filter
        # ----------------------------------------------------------------
        in_stock_raw = request.query_params.get("in_stock")
        in_stock = _parse_bool(in_stock_raw)
        if in_stock is True:
            qs = qs.filter(inventory_quantity__gt=0)
        elif in_stock is False:
            qs = qs.filter(inventory_quantity=0)

        serializer = ProductSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ProductSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProductDetailView(APIView):
    """GET /api/products/<id>/"""

    def get(self, request, pk):
        product = get_object_or_404(Product.objects.select_related("merchant"), pk=pk)
        serializer = ProductSerializer(product)
        return Response(serializer.data)
