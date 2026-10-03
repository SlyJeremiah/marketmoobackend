import datetime
import uuid
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from health.models import Outbreak, OutbreakReport
from market.models import Listing, Pool
from marketmoo.testing import login


def staff_client(phone="+263770000001"):
    u = User.objects.create_user(phone=phone, username=phone, password="pw-for-tests-only", is_staff=True)
    c = APIClient()
    token = c.post("/v1/auth/staff-login", {"username": phone, "password": "pw-for-tests-only"}, format="json").json()["token"]
    c.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    return c, u


class StaffAccessTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_farmer_token_cannot_use_manager_api(self):
        farmer = login()
        for path in ("/v1/manager/stats", "/v1/manager/listings", "/v1/manager/users", "/v1/manager/reports", "/v1/manager/packs"):
            self.assertEqual(farmer.get(path).status_code, 403, path)
        self.assertEqual(APIClient().get("/v1/manager/stats").status_code, 401)

    def test_staff_login_rejects_bad_password_and_non_staff(self):
        User.objects.create_user(phone="+263771000000", username="x", password="pw-for-tests-only")  # not staff
        c = APIClient()
        self.assertEqual(c.post("/v1/auth/staff-login", {"username": "+263771000000", "password": "pw-for-tests-only"}, format="json").status_code, 400)
        User.objects.create_user(phone="+263770000009", username="s", password="right-pw", is_staff=True)
        self.assertEqual(c.post("/v1/auth/staff-login", {"username": "+263770000009", "password": "wrong"}, format="json").status_code, 400)
        self.assertEqual(c.post("/v1/auth/staff-login", {"username": "0770000009", "password": "right-pw"}, format="json").status_code, 200)

    def test_staff_login_is_throttled(self):
        c = APIClient()
        codes = [c.post("/v1/auth/staff-login", {"username": "+263770000009", "password": "nope"}, format="json").status_code for _ in range(12)]
        self.assertIn(429, codes)


class ModerationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.mgr, _ = staff_client()
        owner = User.objects.create_user(phone="+263771111111", username="o")
        self.owner = owner
        self.listing = Listing.objects.create(owner=owner, species="cattle", breed="X", age_months=12, qty=1, price_usd=500,
                                              public_lat=-20.9, public_lon=29.0, phone=owner.phone)

    def test_approve_makes_listing_public(self):
        self.assertEqual(APIClient().get("/v1/listings").json()["count"], 0)
        r = self.mgr.post(f"/v1/manager/listings/{self.listing.pk}/status", {"status": "live"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(APIClient().get("/v1/listings").json()["count"], 1)

    def test_invalid_status_and_unknown_listing(self):
        self.assertEqual(self.mgr.post(f"/v1/manager/listings/{self.listing.pk}/status", {"status": "bogus"}, format="json").status_code, 400)
        self.assertEqual(self.mgr.post(f"/v1/manager/listings/{uuid.uuid4()}/status", {"status": "live"}, format="json").status_code, 404)

    def test_pending_queue_and_verify_seller(self):
        rows = self.mgr.get("/v1/manager/listings", {"status": "pending"}).json()["results"]
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["owner_verified"])
        self.mgr.post(f"/v1/manager/users/{self.owner.pk}/verify", {"verified": True}, format="json")
        self.assertTrue(self.mgr.get("/v1/manager/listings").json()["results"][0]["owner_verified"])

    def test_stats_shape(self):
        s = self.mgr.get("/v1/manager/stats").json()
        self.assertEqual(s["listings"]["by_status"]["pending"], 1)
        self.assertEqual(len(s["series"]["signups"]), 14)
        self.assertGreaterEqual(s["users"]["total"], 2)


class OutbreakWorkflowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.mgr, _ = staff_client()

    def test_report_to_public_notice_workflow(self):
        farmer = login("+263772222222")
        rid = farmer.post("/v1/outbreak-reports", {"species": "Pigs", "suspected": "ASF", "count": 4, "lat": -18.55, "lon": 30.21}, format="json").json()["id"]
        self.assertEqual(self.mgr.get("/v1/manager/reports", {"status": "new"}).json()["count"], 1)
        r = self.mgr.post(f"/v1/manager/reports/{rid}/publish", {"disease": "African Swine Fever", "district": "Mhondoro-Ngezi",
                                                              "control_radius_km": 10, "surveillance_radius_km": 25, "source_url": "https://example.org/dvs"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        pub = APIClient().get("/v1/outbreaks/active").json()["results"][0]
        self.assertEqual(pub["disease"], "African Swine Fever")
        self.assertEqual(pub["centre_lat"], -18.6)  # rounded for privacy
        self.assertEqual(OutbreakReport.objects.get().status, "confirmed")

    def test_outbreak_validation_and_close(self):
        bad = self.mgr.post("/v1/manager/outbreaks", {"disease": "X", "district": "D", "centre_lat": 51.0, "centre_lon": 0.0, "started_on": "2026-10-01"}, format="json")
        self.assertEqual(bad.status_code, 400)
        ok = self.mgr.post("/v1/manager/outbreaks", {"disease": "Anthrax", "district": "Gwanda", "centre_lat": -20.9, "centre_lon": 29.0, "control_radius_km": 5,
                                                   "surveillance_radius_km": 10, "started_on": "2026-10-01"}, format="json")
        self.assertEqual(ok.status_code, 201)
        pk = ok.json()["id"]
        self.mgr.post(f"/v1/manager/outbreaks/{pk}/close", {}, format="json")
        self.assertEqual(APIClient().get("/v1/outbreaks/active").json()["results"], [])

    def test_surveillance_smaller_than_control_is_rejected(self):
        r = self.mgr.post("/v1/manager/outbreaks", {"disease": "X", "district": "D", "centre_lat": -20.9, "centre_lon": 29.0, "control_radius_km": 30,
                                                  "surveillance_radius_km": 10, "started_on": "2026-10-01"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_pool_create_and_status(self):
        r = self.mgr.post("/v1/manager/pools", {"species": "goats", "title": "Beitbridge goats", "target_qty": 100,
                                                "deadline": str(datetime.date.today() + datetime.timedelta(days=30))}, format="json")
        self.assertEqual(r.status_code, 201)
        self.mgr.post(f"/v1/manager/pools/{r.json()['id']}/status", {"status": "lapsed"}, format="json")
        self.assertEqual(Pool.objects.get().status, "lapsed")
        self.assertEqual(APIClient().get("/v1/pools").json()["results"], [])


class PhotoAndStorageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.c = login()

    def test_presign_unavailable_without_storage(self):
        r = self.c.post("/v1/photos/presign", {"listing_id": str(uuid.uuid4())}, format="json")
        self.assertEqual(r.status_code, 503)

    @override_settings(B2_KEY_ID="k", B2_APP_KEY="s", B2_BUCKET="b", B2_S3_ENDPOINT="https://s3.example.test")
    def test_presign_returns_key_scoped_to_user_and_listing(self):
        lid = str(uuid.uuid4())
        with mock.patch("packs.storage.presigned_put", return_value="https://upload.example/url") as p:
            r = self.c.post("/v1/photos/presign", {"listing_id": lid}, format="json").json()
        uid = User.objects.get(phone="+263771234567").id
        self.assertEqual(r["key"], f"listings/{uid}/{lid}.webp")
        p.assert_called_once()
        self.assertEqual(self.c.post("/v1/photos/presign", {"listing_id": "nope"}, format="json").status_code, 400)

    def test_sync_rejects_photo_key_of_another_listing(self):
        from syncapi.tests import listing_op
        op = listing_op()
        op["payload"]["photo_key"] = "listings/999/other.webp"
        res = self.c.post("/v1/sync", {"ops": [op]}, format="json").json()["results"][0]
        self.assertEqual(res["status"], "rejected")

    @override_settings(B2_KEY_ID="k", B2_APP_KEY="s", B2_BUCKET="b", B2_S3_ENDPOINT="https://s3.example.test")
    def test_manifest_uses_presigned_url_when_pack_is_in_b2(self):
        from packs.models import Pack
        Pack.objects.create(district="Gwanda", version="v1", filename="Gwanda-v1.sqlite", size_bytes=10, sha256="0" * 64, storage_key="packs/Gwanda-v1.sqlite")
        with mock.patch("packs.storage.presigned_get", return_value="https://b2.example/signed") as g:
            url = APIClient().get("/v1/packs/manifest").json()["packs"][0]["url"]
        self.assertEqual(url, "https://b2.example/signed")
        g.assert_called_once()


def super_client(phone="+263770000077"):
    User.objects.create_superuser(username=phone, phone=phone, password="pw-for-tests-only")
    c = APIClient()
    token = c.post("/v1/auth/staff-login", {"username": phone, "password": "pw-for-tests-only"}, format="json").json()["token"]
    c.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    return c


class UserManagementTests(TestCase):
    def setUp(self):
        cache.clear()
        self.mgr, self.mgr_user = staff_client()

    def create(self, **over):
        body = {"phone": "0771234567", "role": "farmer", "district": "gwanda"}
        body.update(over)
        return self.mgr.post("/v1/manager/users/create", body, format="json")

    def test_create_user_generates_a_temporary_password_that_works_for_the_app(self):
        r = self.create()
        self.assertEqual(r.status_code, 201, r.content)
        temp = r.json()["temporary_password"]
        self.assertRegex(temp, r"^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$")
        u = User.objects.get(phone="+263771234567")
        self.assertEqual((u.role, u.district, u.is_staff), ("farmer", "gwanda", False))
        # signs in with phone and password, in any phone format, alongside the text code
        for phone in ("0771234567", "+263771234567"):
            lg = APIClient().post("/v1/auth/login", {"phone": phone, "password": temp}, format="json")
            self.assertEqual(lg.status_code, 200)
        self.assertEqual(lg.json()["profile"]["district"], "gwanda")

    def test_wrong_password_unknown_phone_and_inactive_are_refused_the_same_way(self):
        temp = self.create().json()["temporary_password"]
        c = APIClient()
        self.assertEqual(c.post("/v1/auth/login", {"phone": "0771234567", "password": "nope-nope"}, format="json").status_code, 400)
        self.assertEqual(c.post("/v1/auth/login", {"phone": "0779999999", "password": temp}, format="json").status_code, 400)
        uid = User.objects.get(phone="+263771234567").id
        self.mgr.post(f"/v1/manager/users/{uid}/active", {"active": False}, format="json")
        self.assertEqual(c.post("/v1/auth/login", {"phone": "0771234567", "password": temp}, format="json").status_code, 400)

    def test_chosen_password_is_not_echoed_and_must_be_long_enough(self):
        self.assertEqual(self.create(password="short").status_code, 400)
        r = self.create(password="a-long-password-1")
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.json()["temporary_password"])
        self.assertEqual(APIClient().post("/v1/auth/login", {"phone": "0771234567", "password": "a-long-password-1"}, format="json").status_code, 200)

    def test_validation(self):
        self.assertEqual(self.create(phone="12").status_code, 400)
        self.assertEqual(self.create(role="king").status_code, 400)
        self.assertEqual(self.create(district="mars").status_code, 400)
        self.create()
        self.assertEqual(self.create(phone="+263771234567").status_code, 409)  # same number, different format

    def test_only_managers_can_create_and_only_superusers_make_admins(self):
        farmer = login("+263772222222")
        self.assertEqual(farmer.post("/v1/manager/users/create", {"phone": "0773000000"}, format="json").status_code, 403)
        self.assertEqual(self.create(role="admin").status_code, 403)      # plain staff cannot
        sup = super_client()
        r = sup.post("/v1/manager/users/create", {"phone": "0773111111", "role": "admin"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertTrue(User.objects.get(phone="+263773111111").is_staff)

    def test_reset_password_ends_old_sessions_and_old_password(self):
        first = self.create().json()["temporary_password"]
        c = APIClient()
        tok = c.post("/v1/auth/login", {"phone": "0771234567", "password": first}, format="json").json()["token"]
        c.credentials(HTTP_AUTHORIZATION=f"Token {tok}")
        self.assertEqual(c.get("/v1/auth/me").status_code, 200)
        uid = User.objects.get(phone="+263771234567").id
        new = self.mgr.post(f"/v1/manager/users/{uid}/reset-password", {}, format="json").json()["temporary_password"]
        self.assertNotEqual(new, first)
        self.assertEqual(c.get("/v1/auth/me").status_code, 401)
        self.assertEqual(APIClient().post("/v1/auth/login", {"phone": "0771234567", "password": first}, format="json").status_code, 400)
        self.assertEqual(APIClient().post("/v1/auth/login", {"phone": "0771234567", "password": new}, format="json").status_code, 200)

    def test_staff_cannot_touch_other_staff_or_deactivate_themselves(self):
        other, other_user = staff_client("+263770000042")
        self.assertEqual(self.mgr.post(f"/v1/manager/users/{other_user.id}/reset-password", {}, format="json").status_code, 403)
        self.assertEqual(self.mgr.post(f"/v1/manager/users/{other_user.id}/active", {"active": False}, format="json").status_code, 403)
        self.assertEqual(self.mgr.post(f"/v1/manager/users/{self.mgr_user.id}/active", {"active": False}, format="json").status_code, 400)
        self.assertEqual(super_client().post(f"/v1/manager/users/{other_user.id}/active", {"active": False}, format="json").status_code, 200)

    def test_user_list_shows_password_and_active_flags_without_secrets(self):
        self.create()
        row = [u for u in self.mgr.get("/v1/manager/users").json()["results"] if u["phone"] == "+263771234567"][0]
        self.assertTrue(row["has_password"])
        self.assertTrue(row["active"])
        self.assertNotIn("password", row)

    def test_users_who_signed_up_by_text_code_have_no_password_until_they_set_one(self):
        farmer = login("+263774444444")
        row = [u for u in self.mgr.get("/v1/manager/users").json()["results"] if u["phone"] == "+263774444444"][0]
        self.assertFalse(row["has_password"])
        self.assertEqual(farmer.post("/v1/auth/password", {"new_password": "short"}, format="json").status_code, 400)
        self.assertEqual(farmer.post("/v1/auth/password", {"new_password": "my-new-password-1"}, format="json").status_code, 200)
        self.assertEqual(APIClient().post("/v1/auth/login", {"phone": "0774444444", "password": "my-new-password-1"}, format="json").status_code, 200)
        # once a password exists, changing it needs the old one
        self.assertEqual(farmer.post("/v1/auth/password", {"new_password": "another-one-123", "old_password": "wrong"}, format="json").status_code, 400)
        self.assertEqual(farmer.post("/v1/auth/password", {"new_password": "another-one-123", "old_password": "my-new-password-1"}, format="json").status_code, 200)
