import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from marketmoo.testing import login
from market.models import Listing
from records.models import FarmRecord, SyncOp


def record_op(**over):
    p = {"type": "Health / Vaccination", "animal": "Cow A12", "date": "2026-10-02", "cost": 12.5, "notes": "anthrax"}
    p.update(over)
    return {"id": str(uuid.uuid4()), "entity": "record", "entity_id": str(uuid.uuid4()), "payload": p}


def listing_op(**over):
    p = {"species": "Cattle", "breed": "Brahman", "sex": "Male", "age_months": 24, "qty": 2, "price_usd": 850.0, "ward": "Ward 5",
         "public_lat": -20.93412, "public_lon": 29.00871}
    p.update(over)
    return {"id": str(uuid.uuid4()), "entity": "listing", "entity_id": str(uuid.uuid4()), "payload": p}


class SyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.c = login()

    def push(self, *ops, client=None):
        return (client or self.c).post("/v1/sync", {"ops": list(ops)}, format="json")

    def test_requires_authentication(self):
        self.assertEqual(APIClient().post("/v1/sync", {"ops": []}, format="json").status_code, 401)

    def test_record_is_applied_once_even_if_replayed(self):
        op = record_op()
        self.assertEqual(self.push(op).json()["results"][0]["status"], "applied")
        self.assertEqual(self.push(op).json()["results"][0]["status"], "duplicate")
        self.assertEqual(FarmRecord.objects.count(), 1)
        self.assertEqual(SyncOp.objects.count(), 1)

    def test_batch_reports_each_operation_separately(self):
        good, bad = record_op(), record_op(date="not-a-date")
        res = self.push(good, bad).json()["results"]
        self.assertEqual([r["status"] for r in res], ["applied", "rejected"])
        self.assertIn("date", res[1]["error"])

    def test_listing_arrives_pending_and_position_is_blurred(self):
        op = listing_op()
        self.assertEqual(self.push(op).json()["results"][0]["status"], "applied")
        l = Listing.objects.get()
        self.assertEqual(l.status, "pending")  # never trusted to publish itself
        self.assertNotEqual(l.public_lat, -20.93412)
        self.assertLess(abs(l.public_lat - -20.93412) * 111.32, 0.75)
        self.assertEqual(l.phone, "+263771234567")  # phone comes from the account, not the payload

    def test_listing_rejects_position_outside_zimbabwe_and_bad_species(self):
        self.assertEqual(self.push(listing_op(public_lat=51.5, public_lon=-0.1)).json()["results"][0]["status"], "rejected")
        self.assertEqual(self.push(listing_op(species="Dragons")).json()["results"][0]["status"], "rejected")

    def test_cannot_overwrite_someone_elses_record(self):
        op = record_op()
        self.push(op)
        other = login("+263772222222")
        clash = dict(op, id=str(uuid.uuid4()))  # same entity, new operation id
        res = self.push(clash, client=other).json()["results"][0]
        self.assertEqual(res["status"], "rejected")
        self.assertEqual(FarmRecord.objects.get().owner.phone, "+263771234567")

    def test_cannot_reuse_another_users_operation_id(self):
        op = record_op()
        self.push(op)
        other = login("+263772222222")
        self.assertEqual(self.push(op, client=other).json()["results"][0]["status"], "rejected")

    def test_edit_of_live_listing_returns_to_moderation(self):
        op = listing_op()
        self.push(op)
        Listing.objects.update(status="live")
        edit = dict(op, id=str(uuid.uuid4()), payload=dict(op["payload"], price_usd=900.0))
        self.push(edit)
        self.assertEqual(Listing.objects.get().status, "pending")
        self.assertEqual(Listing.objects.get().version, 2)

    def test_limits_and_shape(self):
        self.assertEqual(self.c.post("/v1/sync", {"ops": []}, format="json").status_code, 400)
        self.assertEqual(self.c.post("/v1/sync", {"ops": [record_op() for _ in range(101)]}, format="json").status_code, 400)

    def test_pull_returns_server_status_for_my_listings(self):
        self.push(listing_op())
        Listing.objects.update(status="live")
        body = self.c.get("/v1/sync").json()
        self.assertEqual(body["listings"][0]["status"], "live")
        later = self.c.get("/v1/sync", {"since": body["cursor"]}).json()
        self.assertEqual(later["listings"], [])
