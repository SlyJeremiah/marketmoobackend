import datetime

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from marketmoo.testing import login
from .models import Outbreak, OutbreakReport


class OutbreakTests(TestCase):
    def setUp(self):
        cache.clear()
        call_command("seed_demo", verbosity=0)
        self.c = APIClient()

    def test_seeded_real_event_is_public_and_area_level(self):
        o = self.c.get("/v1/outbreaks/active").json()["results"][0]
        self.assertIn("Foot-and-mouth", o["disease"])
        self.assertEqual(o["district"], "Mangwe")
        self.assertEqual(o["centre_lat"], round(o["centre_lat"], 1))  # rounded to 0.1 degree
        self.assertTrue(o["source_url"].startswith("https://"))

    def test_zone_check_levels(self):
        inside = self.c.get("/v1/outbreaks/zone-check", {"lat": -20.5, "lon": 28.6}).json()
        self.assertEqual(inside["zones"][0]["level"], "control")
        ring = self.c.get("/v1/outbreaks/zone-check", {"lat": -20.5, "lon": 28.85}).json()  # about 26 km east
        self.assertEqual(ring["zones"][0]["level"], "surveillance")
        gwanda = self.c.get("/v1/outbreaks/zone-check", {"lat": -20.93, "lon": 29.0}).json()  # about 60 km away
        self.assertFalse(gwanda["in_zone"])  # agrees with the analysis: Gwanda is outside both rings

    def test_closed_outbreak_is_not_listed(self):
        Outbreak.objects.update(status="closed")
        self.assertEqual(self.c.get("/v1/outbreaks/active").json()["results"], [])

    def test_zone_check_needs_numbers(self):
        self.assertEqual(self.c.get("/v1/outbreaks/zone-check", {"lat": "x"}).status_code, 400)

    def test_reports_are_private_to_reporter(self):
        a, b = login("+263771111111"), login("+263772222222")
        r = a.post("/v1/outbreak-reports", {"species": "Pigs", "suspected": "ASF", "count": 4, "lat": -18.5, "lon": 30.2}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(a.get("/v1/outbreak-reports").json()["results"]), 1)
        self.assertEqual(b.get("/v1/outbreak-reports").json()["results"], [])
        self.assertEqual(self.c.get("/v1/outbreaks/active").json()["results"][0]["district"], "Mangwe")  # report did not become public
        self.assertEqual(OutbreakReport.objects.get().status, "new")
