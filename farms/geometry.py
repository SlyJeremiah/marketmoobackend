"""Validation and measurement of farm boundaries (GeoJSON MultiPolygon in WGS 84, [lon, lat] order).

The server never trusts the phone's numbers: area and centroid are recomputed here, and geometry is checked for
plausibility (inside Zimbabwe, sane size, bounded vertex counts) before it is stored.
"""
import math

LAT_MIN, LAT_MAX = -23.0, -15.0
LON_MIN, LON_MAX = 24.0, 34.0
MAX_POLYGONS = 50
MAX_POINTS_PER_RING = 1500
MAX_POINTS_TOTAL = 5000
MAX_AREA_HA = 200_000  # 2,000 km2: larger than any smallholder or ranch in the pilot districts


class BoundaryError(ValueError):
    pass


def _project(ring, lat0, lon0):
    kx = 111_320.0 * math.cos(math.radians(lat0))
    ky = 110_574.0
    return [((lon - lon0) * kx, (lat - lat0) * ky) for lon, lat in ring]


def _ring_area_centroid(ring):
    """Planar area (m2, positive) and centroid (lon, lat) of a closed ring, projected locally."""
    lat0 = sum(p[1] for p in ring) / len(ring)
    lon0 = sum(p[0] for p in ring) / len(ring)
    pts = _project(ring, lat0, lon0)
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    a /= 2.0
    if abs(a) < 1e-6:
        return 0.0, lon0, lat0
    cx /= 6.0 * a
    cy /= 6.0 * a
    kx = 111_320.0 * math.cos(math.radians(lat0))
    return abs(a), lon0 + cx / kx, lat0 + cy / 110_574.0


def validate_and_measure(geojson):
    """Return (normalised MultiPolygon dict, area_ha, centroid_lat, centroid_lon, vertex_count). Raises BoundaryError."""
    if not isinstance(geojson, dict):
        raise BoundaryError("geometry must be a GeoJSON object")
    kind, coords = geojson.get("type"), geojson.get("coordinates")
    if kind == "Polygon":
        coords = [coords]
    elif kind != "MultiPolygon":
        raise BoundaryError("geometry must be a Polygon or MultiPolygon")
    if not isinstance(coords, list) or not coords:
        raise BoundaryError("geometry has no polygons")
    if len(coords) > MAX_POLYGONS:
        raise BoundaryError(f"at most {MAX_POLYGONS} polygons are allowed")
    out, total_pts = [], 0
    area_m2 = wx = wy = 0.0
    for poly in coords:
        if not isinstance(poly, list) or not poly or not isinstance(poly[0], list):
            raise BoundaryError("each polygon needs an outer ring")
        ring = poly[0]  # holes are ignored on purpose: a farm boundary is the outer edge
        if len(ring) > MAX_POINTS_PER_RING:
            raise BoundaryError(f"a ring has more than {MAX_POINTS_PER_RING} points; simplify the boundary")
        pts = []
        for p in ring:
            try:
                lon, lat = float(p[0]), float(p[1])
            except (TypeError, ValueError, IndexError):
                raise BoundaryError("coordinates must be numbers [lon, lat]")
            if not (math.isfinite(lon) and math.isfinite(lat)):
                raise BoundaryError("coordinates must be finite numbers")
            if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                raise BoundaryError("the boundary is outside Zimbabwe: check the coordinate system")
            pts.append([lon, lat])
        if pts and pts[0] != pts[-1]:
            pts.append(list(pts[0]))
        if len(pts) < 4:
            raise BoundaryError("each ring needs at least 3 distinct points")
        total_pts += len(pts)
        if total_pts > MAX_POINTS_TOTAL:
            raise BoundaryError("too many points in total; simplify the boundary")
        a, cx, cy = _ring_area_centroid(pts)
        if a < 1.0:
            raise BoundaryError("a ring has no area (all points on a line?)")
        area_m2 += a
        wx += cx * a
        wy += cy * a
        out.append([pts])
    area_ha = area_m2 / 10_000.0
    if area_ha > MAX_AREA_HA:
        raise BoundaryError("the boundary is implausibly large (over 200,000 ha)")
    return {"type": "MultiPolygon", "coordinates": out}, area_ha, wy / area_m2, wx / area_m2, total_pts
