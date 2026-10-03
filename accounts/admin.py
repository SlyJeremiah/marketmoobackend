from django.contrib import admin

from .models import OtpCode, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("phone", "role", "district", "verified", "date_joined")
    list_filter = ("role", "district", "verified")
    search_fields = ("phone",)
    exclude = ("password",)


@admin.register(OtpCode)
class OtpAdmin(admin.ModelAdmin):
    list_display = ("phone", "created_at", "attempts", "used")
    exclude = ("code_hash",)
