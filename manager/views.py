"""Manager API used by the React dashboard. Every endpoint requires a staff or admin-role account."""
import datetime

from django.db import models as dj
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from health.models import Outbreak, OutbreakReport
from health.views import OutbreakPublicSerializer
from farms.models import FarmBoundary
from market.models import Listing, Pool
from market.serializers import PoolSerializer
from packs.models import Pack
from records.models import FarmRecord, SyncOp


class IsManager(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_staff or u.role == User.Role.ADMIN))


class ManagerView(APIView):
    permission_classes = [IsManager]


def _series(qs, field, days=14):
    since = timezone.now() - datetime.timedelta(days=days - 1)
    rows = {r["d"]: r["n"] for r in qs.filter(**{f"{field}__gte": since}).annotate(d=TruncDate(field)).values("d").annotate(n=Count("pk")).values("d", "n")}
    today = timezone.localdate()
    return [{"date": str(today - datetime.timedelta(days=i)), "count": rows.get(today - datetime.timedelta(days=i), 0)} for i in range(days - 1, -1, -1)]


class StatsView(ManagerView):
    def get(self, request):
        by_status = {r["status"]: r["n"] for r in Listing.objects.values("status").annotate(n=Count("pk"))}
        return Response({
            "users": {"total": User.objects.count(), "verified": User.objects.filter(verified=True).count(),
                      "by_district": {r["district"]: r["n"] for r in User.objects.values("district").annotate(n=Count("pk"))}},
            "listings": {"by_status": by_status, "total": sum(by_status.values())},
            "records_total": FarmRecord.objects.count(),
            "boundaries": {"count": FarmBoundary.objects.count(), "total_ha": round(FarmBoundary.objects.aggregate(t=dj.Sum("area_ha"))["t"] or 0, 1)},
            "reports": {"new": OutbreakReport.objects.filter(status="new").count(), "total": OutbreakReport.objects.count()},
            "outbreaks_active": Outbreak.objects.filter(status="verified").count(),
            "pools_open": Pool.objects.filter(status="open").count(),
            "sync": {"ops_total": SyncOp.objects.count(), "rejected_total": SyncOp.objects.filter(result="rejected").count()},
            "series": {"signups": _series(User.objects, "date_joined"), "listings": _series(Listing.objects, "created_at"), "sync_ops": _series(SyncOp.objects, "applied_at")},
        })


class ListingRow(serializers.ModelSerializer):
    owner_phone = serializers.CharField(source="owner.phone", read_only=True)
    owner_verified = serializers.BooleanField(source="owner.verified", read_only=True)

    class Meta:
        model = Listing
        fields = ["id", "species", "breed", "sex", "age_months", "qty", "price_usd", "ward", "public_lat", "public_lon", "phone",
                  "photo_key", "status", "owner", "owner_phone", "owner_verified", "created_at", "updated_at"]


class ListingsView(ManagerView):
    def get(self, request):
        qs = Listing.objects.select_related("owner").order_by("-updated_at")
        st = request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        return Response({"count": qs.count(), "results": ListingRow(qs[:200], many=True).data})


class ListingStatusView(ManagerView):
    def post(self, request, pk):
        new = request.data.get("status")
        if new not in {c for c, _ in Listing.Status.choices}:
            return Response({"detail": "Unknown status."}, status=status.HTTP_400_BAD_REQUEST)
        n = Listing.objects.filter(pk=pk).update(status=new, updated_at=timezone.now())
        return Response({"updated": n}, status=status.HTTP_200_OK if n else status.HTTP_404_NOT_FOUND)


class UsersView(ManagerView):
    def get(self, request):
        qs = User.objects.order_by("-date_joined")
        q = request.query_params.get("q")
        if q:
            qs = qs.filter(phone__icontains=q)
        data = [{"id": u.id, "phone": u.phone, "role": u.role, "district": u.district, "verified": u.verified, "joined": u.date_joined,
                 "listings": u.listings.count(), "records": u.records.count()} for u in qs[:200]]
        return Response({"count": qs.count(), "results": data})


class UserVerifyView(ManagerView):
    def post(self, request, pk):
        n = User.objects.filter(pk=pk).update(verified=bool(request.data.get("verified", True)))
        return Response({"updated": n}, status=status.HTTP_200_OK if n else status.HTTP_404_NOT_FOUND)


class ReportRow(serializers.ModelSerializer):
    reporter_phone = serializers.CharField(source="reporter.phone", read_only=True)

    class Meta:
        model = OutbreakReport
        fields = ["id", "species", "suspected", "count", "lat", "lon", "description", "status", "reporter_phone", "created_at"]


class ReportsView(ManagerView):
    def get(self, request):
        qs = OutbreakReport.objects.select_related("reporter").order_by("-created_at")
        st = request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        return Response({"count": qs.count(), "results": ReportRow(qs[:200], many=True).data})


class ReportStatusView(ManagerView):
    def post(self, request, pk):
        new = request.data.get("status")
        if new not in ("new", "reviewing", "confirmed", "dismissed"):
            return Response({"detail": "Unknown status."}, status=status.HTTP_400_BAD_REQUEST)
        n = OutbreakReport.objects.filter(pk=pk).update(status=new)
        return Response({"updated": n}, status=status.HTTP_200_OK if n else status.HTTP_404_NOT_FOUND)


class OutbreakInput(serializers.ModelSerializer):
    class Meta:
        model = Outbreak
        fields = ["disease", "species", "district", "province", "centre_lat", "centre_lon", "control_radius_km", "surveillance_radius_km",
                  "started_on", "ended_on", "summary", "source_url", "location_quality"]

    def validate(self, a):
        if not (-23.0 <= a["centre_lat"] <= -15.0 and 24.0 <= a["centre_lon"] <= 34.0):
            raise serializers.ValidationError("Centre is outside Zimbabwe.")
        if a.get("surveillance_radius_km", 40) < a.get("control_radius_km", 20):
            raise serializers.ValidationError("Surveillance radius must not be smaller than the control radius.")
        return a


class OutbreaksView(ManagerView):
    def get(self, request):
        return Response({"results": [dict(OutbreakPublicSerializer(o).data, centre_lat=o.centre_lat, centre_lon=o.centre_lon) for o in Outbreak.objects.order_by("-started_on")]})

    def post(self, request):
        s = OutbreakInput(data=request.data)
        s.is_valid(raise_exception=True)
        o = s.save(status=Outbreak.Status.VERIFIED)
        return Response({"id": o.pk}, status=status.HTTP_201_CREATED)


class OutbreakPublishFromReportView(ManagerView):
    """Turn a confirmed farmer report into a public, area-level notice (the manager supplies disease and radii)."""

    def post(self, request, pk):
        rep = OutbreakReport.objects.filter(pk=pk).first()
        if rep is None:
            return Response({"detail": "Report not found."}, status=status.HTTP_404_NOT_FOUND)
        data = dict(request.data)
        data.setdefault("species", rep.species)
        data.setdefault("centre_lat", rep.lat)
        data.setdefault("centre_lon", rep.lon)
        data.setdefault("started_on", str(rep.created_at.date()))
        s = OutbreakInput(data=data)
        s.is_valid(raise_exception=True)
        o = s.save(status=Outbreak.Status.VERIFIED)
        rep.status = "confirmed"
        rep.save(update_fields=["status"])
        return Response({"id": o.pk}, status=status.HTTP_201_CREATED)


class OutbreakCloseView(ManagerView):
    def post(self, request, pk):
        n = Outbreak.objects.filter(pk=pk).update(status=Outbreak.Status.CLOSED, ended_on=timezone.localdate())
        return Response({"updated": n}, status=status.HTTP_200_OK if n else status.HTTP_404_NOT_FOUND)


class PoolInput(serializers.ModelSerializer):
    class Meta:
        model = Pool
        fields = ["species", "title", "target_qty", "deadline", "buyer_note", "agg_lat", "agg_lon"]


class PoolsView(ManagerView):
    def get(self, request):
        return Response({"results": PoolSerializer(Pool.objects.order_by("-deadline"), many=True).data})

    def post(self, request):
        s = PoolInput(data=request.data)
        s.is_valid(raise_exception=True)
        return Response({"id": s.save().pk}, status=status.HTTP_201_CREATED)


class PoolStatusView(ManagerView):
    def post(self, request, pk):
        new = request.data.get("status")
        if new not in ("open", "met", "lapsed"):
            return Response({"detail": "Unknown status."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"updated": Pool.objects.filter(pk=pk).update(status=new)})


class PacksView(ManagerView):
    def get(self, request):
        return Response({"results": [{"id": p.pk, "district": p.district, "kind": p.kind, "version": p.version, "size_bytes": p.size_bytes,
                                      "sha256": p.sha256, "stored_in": "b2" if p.storage_key else "local", "created_at": p.created_at} for p in Pack.objects.all()]})
