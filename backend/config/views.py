"""
Project-level views (health check, etc.)
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def health_check(request):
    """
    GET /api/health/
    Returns a simple JSON payload confirming the service is running.
    No authentication required.
    """
    return Response({"status": "ok", "service": "merchant-os-ai"})
