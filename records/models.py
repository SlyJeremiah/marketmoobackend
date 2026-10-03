import uuid

from django.conf import settings
from django.db import models


class FarmRecord(models.Model):
    TYPES = ["Health / Vaccination", "Breeding", "Feed / Water", "Sale", "Expense", "Mortality"]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # client-generated
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="records")
    type = models.CharField(max_length=30)
    animal = models.CharField(max_length=80)
    date = models.DateField()
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-date", "-updated_at"]


class SyncOp(models.Model):
    """Audit trail and idempotency key for every operation pushed by a phone."""

    id = models.UUIDField(primary_key=True)  # the operation UUID chosen by the client
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sync_ops")
    entity = models.CharField(max_length=20)
    entity_id = models.UUIDField()
    payload = models.JSONField()
    result = models.CharField(max_length=10, default="applied")
    error = models.CharField(max_length=200, blank=True)
    applied_at = models.DateTimeField(auto_now_add=True)
