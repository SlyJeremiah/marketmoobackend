from django.contrib import admin

from .models import Listing, Pool, PoolCommitment


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("species", "breed", "qty", "price_usd", "ward", "status", "owner", "updated_at")
    list_filter = ("status", "species")
    search_fields = ("breed", "ward", "owner__phone")
    actions = ["approve", "reject"]

    @admin.action(description="Approve selected listings (make live)")
    def approve(self, request, queryset):
        queryset.update(status=Listing.Status.LIVE)

    @admin.action(description="Reject selected listings")
    def reject(self, request, queryset):
        queryset.update(status=Listing.Status.REJECTED)


admin.site.register(Pool)
admin.site.register(PoolCommitment)
