import uuid

from django.conf import settings
from django.db import models


class FarmBoundary(models.Model):
    """A farmer's farm outline (drawn on the phone or imported from a zipped shapefile).

    PRIVATE: only the owner (and the owner's own deletion) can read the geometry. Listings only ever carry the
    blurred centre, and the manager dashboard sees counts and hectares, never outlines (stock-theft risk).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # chosen by the phone
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="boundary")
    geometry = models.JSONField()
    area_ha = models.FloatField()
    centroid_lat = models.FloatField()
    centroid_lon = models.FloatField()
    vertex_count = models.PositiveIntegerField()
    source = models.CharField(max_length=10, choices=[("drawn", "Drawn on the map"), ("shapefile", "Imported shapefile")], default="drawn")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.owner} {self.area_ha:.1f} ha"
