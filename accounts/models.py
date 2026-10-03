import hashlib
import hmac
import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from datetime import timedelta

from django.db import models
from django.utils import timezone

DISTRICTS = [("mhondoro-ngezi", "Mhondoro-Ngezi"), ("gwanda", "Gwanda"), ("beitbridge", "Beitbridge"), ("other", "Other")]


class User(AbstractUser):
    """Passwordless account identified by phone number. No national ID is stored (Design Document, 13)."""

    class Role(models.TextChoices):
        FARMER = "farmer"
        BUYER = "buyer"
        VET = "vet"
        ADMIN = "admin"

    phone = models.CharField(max_length=20, unique=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.FARMER)
    language = models.CharField(max_length=2, default="en")
    district = models.CharField(max_length=20, choices=DISTRICTS, default="other")
    verified = models.BooleanField(default=False, help_text="Verified seller or expert (set by a manager).")
    consent_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["username"]

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.phone
        if not self.password:
            self.set_unusable_password()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.phone


def normalise_phone(raw: str) -> str:
    """Keep digits and a leading plus; Zimbabwean local numbers (07...) become +263..."""
    s = "".join(ch for ch in raw.strip() if ch.isdigit() or ch == "+")
    if s.startswith("00"):
        s = "+" + s[2:]
    if s.startswith("0") and len(s) >= 9:
        s = "+263" + s[1:]
    if not s.startswith("+"):
        s = "+" + s
    return s


class OtpCode(models.Model):
    phone = models.CharField(max_length=20, db_index=True)
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)

    @staticmethod
    def _hash(phone: str, code: str) -> str:
        key = settings.SECRET_KEY.encode()
        return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()

    @classmethod
    def issue(cls, phone: str):
        """Create a 6-digit code (returned once, stored only as a keyed hash)."""
        code = f"{secrets.randbelow(10**6):06d}"
        row = cls.objects.create(
            phone=phone, code_hash=cls._hash(phone, code),
            expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
        )
        return row, code

    def verify_code(self, code: str) -> bool:
        if self.used or self.attempts >= settings.OTP_MAX_ATTEMPTS or timezone.now() > self.expires_at:
            return False
        self.attempts += 1
        ok = hmac.compare_digest(self.code_hash, self._hash(self.phone, code))
        if ok:
            self.used = True
        self.save(update_fields=["attempts", "used"])
        return ok
