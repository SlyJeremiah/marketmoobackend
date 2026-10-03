import datetime
import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from marketmoo.testing import login
from .geo import blur, haversine_km
from .models import Listing, Pool


def make(owner_phone, lat, lon, status="live", species="cattle", price=500):
    from accounts.models import User
    u, _ = User.objects.get_or_create(phone=owner_phone, defaults={"username": owner_phone})
    return Listing.objects.create(owner=u, species=species, breed="X", age_months=12, qty=1, price_usd=price, public_lat=lat, public_lon=lon, phone=owner_phone, status=status)


class GeoTests(TestCase):
    def test_gwanda_beitbridge_straight_line(self):
        d = haversine_km(-20.93, 29.0, -22.2, 29.99)
        self.assertTrue(150 < d < 190, d)

    def test_blur_is_idempotent_and_small(self):
        v = -20.93412
        self.assertAlmostEqual(blur(blur(v)), blur(v), places=5)
        self.assertLess(abs(blur(v) - v) * 111.32, 0.75)


class FeedTests(TestCase):
    def setUp(self):
        cache.clear()
        self.c = APIClient()

    def test_only_live_listings_are_public(self):
        make("+263771", -20.9, 29.0, status="live")
        make("+263772", -20.9, 29.0, status="pending")
        make("+263773", -20.9, 29.0, status="rejected")
        self.assertEqual(self.c.get("/v1/listings").json()["count"], 1)

    def test_nearest_first_and_radius(self):
        make("+263771", -20.93, 29.00, price=1)   # Gwanda
        make("+263772", -22.20, 29.99, price=2)   # Beitbridge, about 170 km away
        res = self.c.get("/v1/listings", {"near": "-20.95,29.01", "radius": 300}).json()["results"]
        self.assertEqual([float(r["price_usd"]) for r in res], [1.0, 2.0])
        self.assertLess(res[0]["distance_km"], 5)
        far = self.c.get("/v1/listings", {"near": "-20.95,29.01", "radius": 50}).json()
        self.assertEqual(far["count"], 1)

    def test_bad_query_is_400(self):
        self.assertEqual(self.c.get("/v1/listings", {"near": "abc"}).status_code, 400)

    def test_feed_never_exposes_owner_identity_beyond_phone_and_badge(self):
        make("+263771", -20.9, 29.0)
        keys = set(self.c.get("/v1/listings").json()["results"][0])
        self.assertNotIn("owner", keys)
        self.assertIn("seller_verified", keys)


class PoolTests(TestCase):
    def setUp(self):
        cache.clear()
        self.pool = Pool.objects.create(species="goats", title="P", target_qty=10, deadline=datetime.date.today() + datetime.timedelta(days=10))

    def commit(self, c, qty):
        return c.post(f"/v1/pools/{self.pool.pk}/commitments", {"qty": qty, "age_months": 12, "ready_date": str(datetime.date.today())}, format="json")

    def test_commitment_updates_progress_and_closes_when_met(self):
        a, b = login("+263771111111"), login("+263772222222")
        self.assertEqual(self.commit(a, 6).status_code, 201)
        self.assertEqual(APIClient().get("/v1/pools").json()["results"][0]["progress_pct"], 60)
        self.assertEqual(self.commit(b, 5).status_code, 201)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.status, "met")
        # a late commitment is rejected cleanly, the phone shows the message and alternatives
        self.assertEqual(self.commit(login("+263773333333"), 1).status_code, 409)

    def test_same_user_updates_not_duplicates(self):
        a = login()
        self.commit(a, 3)
        self.assertEqual(self.commit(a, 4).status_code, 200)
        self.assertEqual(self.pool.committed(), 4)
