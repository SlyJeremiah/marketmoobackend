from rest_framework import serializers

from packs import storage

from .geo import haversine_km
from .models import Listing, Pool, PoolCommitment


class ListingSerializer(serializers.ModelSerializer):
    seller_verified = serializers.BooleanField(source="owner.verified", read_only=True)
    distance_km = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = ["id", "species", "breed", "sex", "age_months", "qty", "price_usd", "ward", "public_lat", "public_lon",
                  "phone", "status", "seller_verified", "distance_km", "photo_url", "updated_at"]
        read_only_fields = fields

    def get_photo_url(self, obj):
        if not obj.photo_key or not storage.enabled() or self.context.get("data_saver"):
            return None
        return storage.presigned_get(obj.photo_key)

    def get_distance_km(self, obj):
        c = self.context.get("center")
        return round(haversine_km(c[0], c[1], obj.public_lat, obj.public_lon), 1) if c else None


class PoolSerializer(serializers.ModelSerializer):
    committed = serializers.SerializerMethodField()
    progress_pct = serializers.SerializerMethodField()

    class Meta:
        model = Pool
        fields = ["id", "species", "title", "target_qty", "deadline", "status", "buyer_note", "agg_lat", "agg_lon", "committed", "progress_pct"]

    def get_committed(self, obj):
        return obj.committed()

    def get_progress_pct(self, obj):
        return min(100, round(100 * obj.committed() / obj.target_qty)) if obj.target_qty else 0


class CommitmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PoolCommitment
        fields = ["id", "pool", "qty", "age_months", "ready_date", "status"]
        read_only_fields = ["id", "pool", "status"]
