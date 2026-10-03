from django.contrib import admin

from .models import FarmRecord, SyncOp

admin.site.register(FarmRecord)


@admin.register(SyncOp)
class SyncOpAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "entity", "result", "applied_at")
    list_filter = ("entity", "result")
