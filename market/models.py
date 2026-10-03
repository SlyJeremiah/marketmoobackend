import uuid

from django.conf import settings
from django.db import models


class Listing(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending moderation"
        LIVE = "live", "Live"
        SOLD = "sold", "Sold"
        REMOVED = "removed", "Removed"
        REJECTED = "rejected", "Rejected"

    SPECIES = [("cattle", "Cattle"), ("goats", "Goats"), ("sheep", "Sheep"), ("pigs", "Pigs"), ("poultry", "Poultry")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # client-generated on the phone
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listings")
    species = models.CharField(max_length=10, choices=SPECIES)
    breed = models.CharField(max_length=60)
    sex = models.CharField(max_length=10, default="Mixed")
    age_months = models.PositiveSmallIntegerField()
    qty = models.PositiveIntegerField(default=1)
    price_usd = models.DecimalField(max_digits=9, decimal_places=2)
    ward = models.CharField(max_length=80, blank=True)
    # Only the blurred position is ever stored (about 1 km); the precise pin stays on the owner's phone.
    public_lat = models.FloatField()
    public_lon = models.FloatField()
    phone = models.CharField(max_length=20)
    photo_key = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["status", "species"]), models.Index(fields=["public_lat", "public_lon"])]

    def __str__(self):
        return f"{self.species} {self.breed} x{self.qty}"


class Pool(models.Model):
    species = models.CharField(max_length=10, choices=Listing.SPECIES)
    title = models.CharField(max_length=120)
    target_qty = models.PositiveIntegerField()
    deadline = models.DateField()
    status = models.CharField(max_length=10, default="open", choices=[("open", "Open"), ("met", "Target met"), ("lapsed", "Lapsed")])
    buyer_note = models.CharField(max_length=200, blank=True)
    agg_lat = models.FloatField(null=True, blank=True)
    agg_lon = models.FloatField(null=True, blank=True)

    def committed(self):
        return self.commitments.filter(status="active").aggregate(s=models.Sum("qty"))["s"] or 0

    def __str__(self):
        return self.title


class PoolCommitment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pool = models.ForeignKey(Pool, on_delete=models.CASCADE, related_name="commitments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    qty = models.PositiveIntegerField()
    age_months = models.PositiveSmallIntegerField()
    ready_date = models.DateField()
    status = models.CharField(max_length=10, default="active", choices=[("active", "Active"), ("released", "Released"), ("rejected", "Rejected")])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("pool", "user")]
