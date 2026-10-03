from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def ping(_request):
    """1-byte health check: lets the app test connectivity and wakes a sleeping free-tier server."""
    return HttpResponse("1", content_type="text/plain")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("v1/ping", ping),
    path("v1/auth/", include("accounts.urls")),
    path("v1/", include("market.urls")),
    path("v1/", include("health.urls")),
    path("v1/", include("packs.urls")),
    path("v1/", include("syncapi.urls")),
    path("v1/", include("farms.urls")),
    path("v1/manager/", include("manager.urls")),
]
