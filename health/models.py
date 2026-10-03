import uuid

from django.conf import settings
from django.db import models


class Outbreak(models.Model):
    """A notice published by a manager after verification (ideally confirmed with DVS).

    Only area-level information is ever exposed publicly: a rounded centre and a radius, never a farm.
    """

    class Status(models.TextChoices):
        VERIFIED = "verified", "Verified"
        CLOSED = "closed", "Closed"

    disease = models.CharField(max_length=80)
    species = models.CharField(max_length=40, blank=True)
    district = models.CharField(max_length=60)
    province = models.CharField(max_length=60, blank=True)
    centre_lat = models.FloatField()
    centre_lon = models.FloatField()
    control_radius_km = models.FloatField(default=20, help_text="Reported control or vaccination radius.")
    surveillance_radius_km = models.FloatField(default=40, help_text="Assumed surveillance ring (set by DVS).")
    started_on = models.DateField()
    ended_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.VERIFIED)
    summary = models.CharField(max_length=300, blank=True)
    source_url = models.URLField(blank=True)
    location_quality = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return f"{self.disease} - {self.district} ({self.started_on})"


class OutbreakReport(models.Model):
    """A suspected outbreak reported by a farmer. Never public until a manager turns it into an Outbreak."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="outbreak_reports")
    species = models.CharField(max_length=40)
    suspected = models.CharField(max_length=80, blank=True)
    count = models.PositiveIntegerField(default=1)
    lat = models.FloatField()
    lon = models.FloatField()
    description = models.TextField(blank=True)
    status = models.CharField(max_length=12, default="new", choices=[("new", "New"), ("reviewing", "Reviewing"), ("confirmed", "Confirmed"), ("dismissed", "Dismissed")])
    created_at = models.DateTimeField(auto_now_add=True)
