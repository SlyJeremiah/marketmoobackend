import math
import uuid

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from marketmoo.testing import login

from .geometry import BoundaryError, validate_and_measure
from .models import FarmBoundary

# a roughly 100 m x 100 m square near Gwanda (about 1 hectare)
LAT0, LON0 = -20.9300, 29.0000
DLAT = 100 / 110_574.0
DLON = 100 / (111_320.0 * math.cos(math.radians(LAT0)))


def square(lat=LAT0, lon=LON0, kind="MultiPolygon"):
    ring = [[lon, lat], [lon + DLON, lat], [lon + DLON, lat + DLAT], [lon, lat + DLAT], [lon, lat]]
    return {"type": "Polygon", "coordinates": [ring]} if kind == "Polygon" else {"type": "MultiPolygon", "coordinates": [[ring]]}


def op(payload, entity_id=None):
    return {"id": str(uuid.uuid4()), "entity": "farm_boundary", "entity_id": entity_id or str(uuid.uuid4()), "payload": payload}


class GeometryTests(SimpleTestCase):
    def test_area_and_centroid_of_one_hectare(self):
        geom, ha, lat, lon, n = validate_and_measure(square())
        self.assertAlmostEqual(ha, 1.0, delta=0.03)
        self.assertAlmostEqual(lat, LAT0 + DLAT / 2, places=5)
        self.assertAlmostEqual(lon, LON0 + DLON / 2, places=5)
        self.assertEqual(n, 5)

    def test_polygon_is_accepted_and_open_ring_is_closed(self):
        g = square(kind="Polygon")
        g["coordinates"][0] = g["coordinates"][0][:-1]
        geom, ha, *_ = validate_and_measure(g)
        self.assertEqual(geom["type"], "MultiPolygon")
        self.assertEqual(geom["coordinates"][0][0][0], geom["coordinates"][0][0][-1])

    def test_rejections(self):
        far = {"type": "Polygon", "coordinates": [[[0, 51], [1, 51], [1, 52], [0, 52], [0, 51]]]}
        for bad, text in [
            (far, "outside Zimbabwe"),
            ({"type": "Point", "coordinates": [29, -20]}, "Polygon or MultiPolygon"),
            ({"type": "Polygon", "coordinates": [[[29, -20.9], [29.001, -20.9], [29, -20.9]]]}, "3 distinct"),
            ({"type": "Polygon", "coordinates": [[[29, -20.9], [29.001, -20.9], [29.002, -20.9], [29, -20.9]]]}, "no area"),
            ({"type": "Polygon", "coordinates": [[["a", "b"], [1, 2], [3, 4], ["a", "b"]]]}, "numbers"),
            ("nope", "GeoJSON"),
        ]:
            with self.assertRaises(BoundaryError, msg=text) as cm:
                validate_and_measure(bad)
            self.assertIn(text, str(cm.exception))

    def test_too_many_points_and_implausible_size(self):
        ring = [[29 + i * 1e-6, -20.9 + (i % 2) * 1e-6] for i in range(1600)]
        with self.assertRaises(BoundaryError):
            validate_and_measure({"type": "Polygon", "coordinates": [ring + [ring[0]]]})
        huge = {"type": "Polygon", "coordinates": [[[25, -22], [33, -22], [33, -16], [25, -16], [25, -22]]]}
        with self.assertRaises(BoundaryError) as cm:
            validate_and_measure(huge)
        self.assertIn("large", str(cm.exception))

    def test_two_polygons_add_up(self):
        a = square()["coordinates"][0]
        b = square(lat=-20.95)["coordinates"][0]
        _, ha, *_ = validate_and_measure({"type": "MultiPolygon", "coordinates": [a, b]})
        self.assertAlmostEqual(ha, 2.0, delta=0.06)


class BoundarySyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.c = login()

    def push(self, *ops, client=None):
        return (client or self.c).post("/v1/sync", {"ops": list(ops)}, format="json").json()["results"]

    def test_valid_boundary_is_stored_with_server_measured_area(self):
        eid = str(uuid.uuid4())
        r = self.push(op({"geometry": square(), "source": "drawn", "area_ha": 9999}, eid))  # a lying client is ignored
        self.assertEqual(r[0]["status"], "applied")
        b = FarmBoundary.objects.get()
        self.assertAlmostEqual(b.area_ha, 1.0, delta=0.03)
        self.assertEqual(str(b.id), eid)
        self.assertEqual(b.source, "drawn")

    def test_replay_is_idempotent_and_resave_replaces(self):
        o = op({"geometry": square(), "source": "shapefile"})
        self.assertEqual(self.push(o)[0]["status"], "applied")
        self.assertEqual(self.push(o)[0]["status"], "duplicate")
        bigger = square()
        bigger["coordinates"][0][0][2][1] += DLAT  # stretch to two hectares
        bigger["coordinates"][0][0][3][1] += DLAT
        self.assertEqual(self.push(op({"geometry": bigger, "source": "drawn"}))[0]["status"], "applied")
        self.assertEqual(FarmBoundary.objects.count(), 1)  # one boundary per farmer
        self.assertAlmostEqual(FarmBoundary.objects.get().area_ha, 2.0, delta=0.06)

    def test_bad_geometry_and_source_are_rejected_with_reasons(self):
        far = {"type": "Polygon", "coordinates": [[[0, 51], [1, 51], [1, 52], [0, 52], [0, 51]]]}
        r = self.push(op({"geometry": far}), op({"geometry": square(), "source": "magic"}), op({}))
        self.assertEqual([x["status"] for x in r], ["rejected"] * 3)
        self.assertIn("outside Zimbabwe", r[0]["error"])
        self.assertFalse(FarmBoundary.objects.exists())

    def test_owner_isolation(self):
        eid = str(uuid.uuid4())
        self.push(op({"geometry": square()}, eid))
        other = login("+263772222222")
        r = self.push(op({"geometry": square(lat=-20.5)}, eid), client=other)
        self.assertEqual(r[0]["status"], "rejected")
        self.assertEqual(other.get("/v1/farm/boundary").status_code, 404)  # cannot read someone else's outline
        self.assertEqual(self.c.get("/v1/farm/boundary").status_code, 200)

    def test_get_returns_only_my_geometry_and_delete_removes_it(self):
        self.push(op({"geometry": square(), "source": "shapefile"}))
        body = self.c.get("/v1/farm/boundary").json()
        self.assertEqual(body["source"], "shapefile")
        self.assertEqual(body["geometry"]["type"], "MultiPolygon")
        self.assertEqual(self.c.delete("/v1/farm/boundary").status_code, 204)
        self.assertEqual(self.c.get("/v1/farm/boundary").status_code, 404)

    def test_deleted_flag_through_sync(self):
        self.push(op({"geometry": square()}))
        self.assertEqual(self.push(op({"deleted": True}))[0]["status"], "applied")
        self.assertFalse(FarmBoundary.objects.exists())

    def test_requires_login(self):
        self.assertEqual(APIClient().get("/v1/farm/boundary").status_code, 401)

    def test_outline_never_leaks_through_public_or_manager_endpoints(self):
        from accounts.models import User
        from manager.tests import staff_client
        self.push(op({"geometry": square()}))
        mgr, _ = staff_client("+263770000055")
        stats = mgr.get("/v1/manager/stats").json()
        self.assertEqual(stats["boundaries"]["count"], 1)
        self.assertAlmostEqual(stats["boundaries"]["total_ha"], 1.0, delta=0.1)
        blob = mgr.get("/v1/manager/users").content + mgr.get("/v1/manager/listings").content + APIClient().get("/v1/listings").content
        self.assertNotIn(b"coordinates", blob)
        self.assertFalse(User.objects.filter(phone="+263770000055").first() is None)
