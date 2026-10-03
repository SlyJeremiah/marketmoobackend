from django.test import override_settings
from rest_framework.test import APIClient

SMS = "accounts.sms.LocmemSmsBackend"


def login(phone="+263771234567", client=None):
    """Run the real OTP flow and return a client authenticated with the issued token."""
    client = client or APIClient()
    with override_settings(OTP_DEV_ECHO=True, SMS_BACKEND=SMS):
        code = client.post("/v1/auth/otp/request", {"phone": phone}, format="json").json()["dev_code"]
        token = client.post("/v1/auth/otp/verify", {"phone": phone, "code": code, "consent": True}, format="json").json()["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    return authed
