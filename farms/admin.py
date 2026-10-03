from django.contrib import admin

from .models import FarmBoundary


@admin.register(FarmBoundary)
class FarmBoundaryAdmin(admin.ModelAdmin):
    list_display = ("owner", "area_ha", "source", "vertex_count", "updated_at")
    exclude = ("geometry",)  # outlines are private; the admin shows size only
