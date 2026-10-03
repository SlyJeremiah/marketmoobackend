from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from packs import storage

from .geo import bbox, haversine_km
from .models import Listing, Pool, PoolCommitment
from .serializers import CommitmentSerializer, ListingSerializer, PoolSerializer


class ListingFeedView(APIView):
    """Public feed of LIVE listings, optionally filtered by species and sorted by distance from near=lat,lon."""
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        qs = Listing.objects.filter(status=Listing.Status.LIVE).select_related("owner")
        species = request.query_params.get("species")
        if species:
            qs = qs.filter(species=species)
        center = None
        radius = 150.0
        near = request.query_params.get("near")
        if near:
            try:
                lat, lon = (float(x) for x in near.split(","))
                radius = float(request.query_params.get("radius", 150))
            except ValueError:
                return Response({"detail": "near must be lat,lon and radius a number."}, status=status.HTTP_400_BAD_REQUEST)
            s, n, w, e = bbox(lat, lon, radius)
            qs = qs.filter(public_lat__range=(s, n), public_lon__range=(w, e))
            center = (lat, lon)
        items = list(qs[:500])
        if center:
            items = [i for i in items if haversine_km(center[0], center[1], i.public_lat, i.public_lon) <= radius]
            items.sort(key=lambda i: haversine_km(center[0], center[1], i.public_lat, i.public_lon))
        data = ListingSerializer(items[:100], many=True, context={"center": center, "data_saver": request.query_params.get("data_saver") == "1"}).data
        return Response({"count": len(items), "results": data})


class MyListingsView(generics.ListAPIView):
    serializer_class = ListingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Listing.objects.filter(owner=self.request.user).order_by("-updated_at")


class PoolListView(generics.ListAPIView):
    serializer_class = PoolSerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []
    queryset = Pool.objects.filter(status="open").order_by("deadline")


class PoolCommitView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        pool = Pool.objects.select_for_update().filter(pk=pk).first()
        if pool is None:
            return Response({"detail": "Pool not found."}, status=status.HTTP_404_NOT_FOUND)
        if pool.status != "open":
            return Response({"detail": "This pool is closed."}, status=status.HTTP_409_CONFLICT)  # server-authoritative
        s = CommitmentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj, created = PoolCommitment.objects.update_or_create(pool=pool, user=request.user, defaults={**s.validated_data, "status": "active"})
        if pool.committed() >= pool.target_qty:
            pool.status = "met"
            pool.save(update_fields=["status"])
        return Response(CommitmentSerializer(obj).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PhotoPresignView(APIView):
    """Returns a short-lived URL so the phone uploads a (resized) photo straight to B2. The key is deterministic,
    so the listing sync only has to carry the key; the API never handles image bytes."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        listing_id = request.data.get("listing_id")
        try:
            import uuid as _uuid
            lid = str(_uuid.UUID(str(listing_id)))
        except ValueError:
            return Response({"detail": "listing_id must be a UUID."}, status=status.HTTP_400_BAD_REQUEST)
        if not storage.enabled():
            return Response({"detail": "Photo storage is not configured on this server."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        key = photo_key_for(request.user.id, lid)
        return Response({"key": key, "upload_url": storage.presigned_put(key), "content_type": "image/webp", "max_bytes": 150_000})


def photo_key_for(user_id, listing_id):
    return f"listings/{user_id}/{listing_id}.webp"
