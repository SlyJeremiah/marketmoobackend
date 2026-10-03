from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from marketmoo.testing import SMS, login

from .models import OtpCode, User, normalise_phone


class PhoneTests(TestCase):
    def test_local_number_becomes_international(self):
        self.assertEqual(normalise_phone("0771 234 567"), "+263771234567")
        self.assertEqual(normalise_phone("00263771234567"), "+263771234567")


@override_settings(OTP_DEV_ECHO=True, SMS_BACKEND=SMS)
class OtpFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.c = APIClient()

    def test_full_flow_creates_user_and_token(self):
        r = self.c.post("/v1/auth/otp/request", {"phone": "0771234567"}, format="json")
        self.assertEqual(r.status_code, 200)
        code = r.json()["dev_code"]
        v = self.c.post("/v1/auth/otp/verify", {"phone": "0771234567", "code": code, "consent": True}, format="json")
        self.assertEqual(v.status_code, 200)
        self.assertTrue(v.json()["created"])
        u = User.objects.get(phone="+263771234567")
        self.assertFalse(u.has_usable_password())
        self.assertIsNotNone(u.consent_at)

    def test_code_is_stored_hashed_and_single_use(self):
        r = self.c.post("/v1/auth/otp/request", {"phone": "+263771234567"}, format="json")
        code = r.json()["dev_code"]
        row = OtpCode.objects.get()
        self.assertNotIn(code, row.code_hash)
        self.assertEqual(self.c.post("/v1/auth/otp/verify", {"phone": "+263771234567", "code": code}, format="json").status_code, 200)
        self.assertEqual(self.c.post("/v1/auth/otp/verify", {"phone": "+263771234567", "code": code}, format="json").status_code, 400)

    def test_wrong_code_locks_after_five_attempts(self):
        self.c.post("/v1/auth/otp/request", {"phone": "+263771234567"}, format="json")
        for _ in range(5):
            self.assertEqual(self.c.post("/v1/auth/otp/verify", {"phone": "+263771234567", "code": "000000"}, format="json").status_code, 400)
        row = OtpCode.objects.get()
        self.assertEqual(row.attempts, 5)

    def test_per_number_limit(self):
        for _ in range(5):
            self.assertEqual(self.c.post("/v1/auth/otp/request", {"phone": "+263771234567"}, format="json").status_code, 200)
        cache.clear()  # isolate the per-number rule from the per-IP throttle
        self.assertEqual(self.c.post("/v1/auth/otp/request", {"phone": "+263771234567"}, format="json").status_code, 429)

    def test_otp_echo_is_off_when_not_configured(self):
        with override_settings(OTP_DEV_ECHO=False):
            body = self.c.post("/v1/auth/otp/request", {"phone": "+263771234567"}, format="json").json()
        self.assertNotIn("dev_code", body)

    def test_profile_cannot_self_promote_to_admin(self):
        c = login()
        self.assertEqual(c.patch("/v1/auth/me", {"role": "admin"}, format="json").status_code, 403)
        self.assertEqual(c.patch("/v1/auth/me", {"role": "buyer", "district": "gwanda"}, format="json").status_code, 200)

    def test_delete_my_data_removes_account(self):
        c = login()
        self.assertEqual(c.delete("/v1/auth/me").status_code, 204)
        self.assertFalse(User.objects.filter(phone="+263771234567").exists())
