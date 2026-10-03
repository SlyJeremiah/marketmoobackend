from django.contrib import admin

from .models import Outbreak, OutbreakReport


@admin.register(Outbreak)
class OutbreakAdmin(admin.ModelAdmin):
    list_display = ("disease", "district", "started_on", "status", "control_radius_km", "surveillance_radius_km")
    list_filter = ("status", "disease")


@admin.register(OutbreakReport)
class OutbreakReportAdmin(admin.ModelAdmin):
    list_display = ("suspected", "species", "count", "status", "created_at")
    list_filter = ("status",)
    actions = ["mark_reviewing", "mark_dismissed"]

    @admin.action(description="Mark as reviewing (contact DVS)")
    def mark_reviewing(self, request, queryset):
        queryset.update(status="reviewing")

    @admin.action(description="Dismiss")
    def mark_dismissed(self, request, queryset):
        queryset.update(status="dismissed")
