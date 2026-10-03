"""POST /v1/sync (push operations) and GET /v1/sync?since= (pull changes).

Rules (Design Document, Section 5.4):
- every operation carries a client UUID; replays return `duplicate` and change nothing (idempotent)
- the server never trusts the client for ownership or moderation: listings always arrive `pending`
- the precise farm location never leaves the phone: only public_lat/public_lon (blurred again here) are stored
"""
import datetime
import uuid
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from health.models import OutbreakReport
from market.geo import blur
from farms.geometry import BoundaryError, validate_and_measure
from farms.models import FarmBoundary
from market.models import Listing
from market.views import photo_key_for
from records.models import FarmRecord, SyncOp

MAX_OPS = 100
SPECIES = {s for s, _ in Listing.SPECIES}


class OpError(Exception):
    pass


def _uuid(v, name):
    try:
        return uuid.UUID(str(v))
    except ValueError:
        raise OpError(f"{name} must be a UUID")


def _req(p, key):
    if key not in p or p[key] in (None, ""):
        raise OpError(f"missing {key}")
    return p[key]


def apply_record(user, entity_id, p):
    try:
        date = datetime.date.fromisoformat(str(_req(p, "date")))
    except ValueError:
        raise OpError("date must be YYYY-MM-DD")
    cost = p.get("cost")
    try:
        cost = Decimal(str(cost)) if cost is not None else None
    except InvalidOperation:
        raise OpError("cost must be a number")
    if cost is not None and cost < 0:
        raise OpError("cost must not be negative")
    obj = FarmRecord.objects.filter(pk=entity_id).first()
    if obj and obj.owner_id != user.id:
        raise OpError("not your record")
    vals = dict(type=str(_req(p, "type"))[:30], animal=str(_req(p, "animal"))[:80], date=date, cost=cost, notes=str(p.get("notes", ""))[:2000])
    if obj:
        for k, v in vals.items():
            setattr(obj, k, v)
        obj.version += 1
        obj.save()
    else:
        FarmRecord.objects.create(pk=entity_id, owner=user, **vals)


def apply_listing(user, entity_id, p):
    species = str(_req(p, "species")).lower()
    if species not in SPECIES:
        raise OpError("unknown species")
    try:
        price = Decimal(str(_req(p, "price_usd")))
        qty = int(_req(p, "qty"))
        age = int(_req(p, "age_months"))
        lat, lon = float(_req(p, "public_lat")), float(_req(p, "public_lon"))
    except (InvalidOperation, ValueError):
        raise OpError("price, qty, age and position must be numbers")
    if price <= 0 or qty < 1 or age < 0:
        raise OpError("price must be positive, quantity at least 1")
    if not (-23.0 <= lat <= -15.0 and 24.0 <= lon <= 34.0):
        raise OpError("position is outside Zimbabwe")
    obj = Listing.objects.filter(pk=entity_id).first()
    if obj and obj.owner_id != user.id:
        raise OpError("not your listing")
    photo = p.get("photo_key") or ""
    if photo and photo != photo_key_for(user.id, entity_id):
        raise OpError("photo_key does not match this listing")
    vals = dict(species=species, breed=str(_req(p, "breed"))[:60], sex=str(p.get("sex", "Mixed"))[:10], age_months=age, qty=qty,
                price_usd=price, ward=str(p.get("ward", ""))[:80], public_lat=blur(lat), public_lon=blur(lon), phone=user.phone, photo_key=photo)
    if obj:
        for k, v in vals.items():
            setattr(obj, k, v)
        obj.version += 1
        # status is server-authoritative: an edit never changes moderation state except to re-check live listings
        obj.status = Listing.Status.PENDING if obj.status == Listing.Status.LIVE else obj.status
        obj.save()
    else:
        Listing.objects.create(pk=entity_id, owner=user, status=Listing.Status.PENDING, **vals)


def apply_outbreak_report(user, entity_id, p):
    try:
        lat, lon = float(_req(p, "lat")), float(_req(p, "lon"))
        count = int(p.get("count", 1))
    except ValueError:
        raise OpError("lat, lon and count must be numbers")
    if OutbreakReport.objects.filter(pk=entity_id).exists():
        return
    OutbreakReport.objects.create(pk=entity_id, reporter=user, species=str(_req(p, "species"))[:40], suspected=str(p.get("suspected", ""))[:80],
                                  count=max(count, 1), lat=lat, lon=lon, description=str(p.get("description", ""))[:2000])


def apply_farm_boundary(user, entity_id, p):
    """One boundary per farmer. The server recomputes area and centroid and rejects implausible geometry."""
    if p.get("deleted"):
        FarmBoundary.objects.filter(owner=user).delete()
        return
    source = p.get("source", "drawn")
    if source not in ("drawn", "shapefile"):
        raise OpError("source must be drawn or shapefile")
    try:
        geom, area_ha, lat, lon, n = validate_and_measure(p.get("geometry"))
    except BoundaryError as e:
        raise OpError(str(e))
    other = FarmBoundary.objects.filter(pk=entity_id).exclude(owner=user).exists()
    if other:
        raise OpError("not your boundary")
    vals = dict(geometry=geom, area_ha=area_ha, centroid_lat=lat, centroid_lon=lon, vertex_count=n, source=source)
    b = FarmBoundary.objects.filter(owner=user).first()
    if b:
        for k, v in vals.items():
            setattr(b, k, v)
        b.save()
    else:
        FarmBoundary.objects.create(pk=entity_id, owner=user, **vals)


HANDLERS = {"record": apply_record, "listing": apply_listing, "outbreak_report": apply_outbreak_report, "farm_boundary": apply_farm_boundary}


class SyncView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ops = request.data.get("ops") if isinstance(request.data, dict) else None
        if not isinstance(ops, list) or not ops:
            return Response({"detail": "ops must be a non-empty list."}, status=status.HTTP_400_BAD_REQUEST)
        if len(ops) > MAX_OPS:
            return Response({"detail": f"At most {MAX_OPS} operations per request."}, status=status.HTTP_400_BAD_REQUEST)
        results = []
        for op in ops:
            op_id = None
            try:
                if not isinstance(op, dict):
                    raise OpError("operation must be an object")
                op_id = _uuid(op.get("id"), "id")
                entity = op.get("entity")
                if entity not in HANDLERS:
                    raise OpError("unknown entity")
                entity_id = _uuid(op.get("entity_id"), "entity_id")
                payload = op.get("payload")
                if not isinstance(payload, dict):
                    raise OpError("payload must be an object")
                existing = SyncOp.objects.filter(pk=op_id).first()
                if existing:
                    if existing.user_id != request.user.id:
                        raise OpError("operation id already used")
                    results.append({"id": str(op_id), "status": "duplicate"})
                    continue
                with transaction.atomic():
                    HANDLERS[entity](request.user, entity_id, payload)
                    SyncOp.objects.create(id=op_id, user=request.user, entity=entity, entity_id=entity_id, payload=payload)
                results.append({"id": str(op_id), "status": "applied"})
            except OpError as e:
                results.append({"id": str(op_id) if op_id else None, "status": "rejected", "error": str(e)})
            except IntegrityError:
                results.append({"id": str(op_id) if op_id else None, "status": "rejected", "error": "conflict"})
        return Response({"results": results, "cursor": timezone.now().isoformat()})

    def get(self, request):
        """Delta pull: my records and listings changed since the cursor (ISO time). Server status wins on the phone."""
        since = parse_datetime(request.query_params.get("since", "")) if request.query_params.get("since") else None
        recs = FarmRecord.objects.filter(owner=request.user)
        lsts = Listing.objects.filter(owner=request.user)
        if since:
            recs, lsts = recs.filter(updated_at__gt=since), lsts.filter(updated_at__gt=since)
        return Response({
            "cursor": timezone.now().isoformat(),
            "records": [{"id": str(r.id), "version": r.version, "updated_at": r.updated_at.isoformat()} for r in recs[:500]],
            "listings": [{"id": str(l.id), "status": l.status, "version": l.version, "updated_at": l.updated_at.isoformat()} for l in lsts[:500]],
        })
