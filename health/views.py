from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from market.geo import haversine_km

from .models import Outbreak, OutbreakReport


class OutbreakPublicSerializer(serializers.ModelSerializer):
    centre_lat = serializers.SerializerMethodField()
    centre_lon = serializers.SerializerMethodField()

    class Meta:
        model = Outbreak
        fields = ["id", "disease", "species", "district", "province", "centre_lat", "centre_lon", "control_radius_km",
                  "surveillance_radius_km", "started_on", "ended_on", "status", "summary", "source_url", "location_quality"]

    # Area-level only: round to 0.1 degree (about 11 km) so no individual premises can be pinpointed.
    def get_centre_lat(self, o):
        return round(o.centre_lat, 1)

    def get_centre_lon(self, o):
        return round(o.centre_lon, 1)


class ActiveOutbreaksView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        qs = Outbreak.objects.filter(status=Outbreak.Status.VERIFIED)
        district = request.query_params.get("district")
        if district:
            qs = qs.filter(district__iexact=district)
        return Response({"results": OutbreakPublicSerializer(qs, many=True).data})


class ZoneCheckView(APIView):
    """Is this point inside a control or surveillance zone? (The phone does the same check locally from its pack.)"""
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        try:
            lat, lon = float(request.query_params["lat"]), float(request.query_params["lon"])
        except (KeyError, ValueError):
            return Response({"detail": "lat and lon are required numbers."}, status=status.HTTP_400_BAD_REQUEST)
        hits = []
        for o in Outbreak.objects.filter(status=Outbreak.Status.VERIFIED):
            d = haversine_km(lat, lon, o.centre_lat, o.centre_lon)
            level = "control" if d <= o.control_radius_km else "surveillance" if d <= o.surveillance_radius_km else None
            if level:
                hits.append({"disease": o.disease, "level": level, "district": o.district, "source_url": o.source_url})
        return Response({"in_zone": bool(hits), "zones": hits})


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutbreakReport
        fields = ["id", "species", "suspected", "count", "lat", "lon", "description", "status", "created_at"]
        read_only_fields = ["status", "created_at"]
        extra_kwargs = {"id": {"required": False}}


class ReportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = ReportSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(reporter=request.user)
        return Response(s.data, status=status.HTTP_201_CREATED)

    def get(self, request):
        return Response({"results": ReportSerializer(OutbreakReport.objects.filter(reporter=request.user), many=True).data})
