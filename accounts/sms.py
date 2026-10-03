"""SMS delivery. The trial uses a console backend; a real gateway (one that reaches Zimbabwean numbers) plugs in here.

Set MARKETMOO_SMS_BACKEND to the dotted path of another class with a `send(phone, text)` method.
"""
import logging

logger = logging.getLogger("marketmoo.sms")


class ConsoleSmsBackend:
    def send(self, phone: str, text: str) -> None:
        # Never log real codes in production: this backend is only meant for development and tests.
        logger.warning("SMS to %s: %s", phone, text)


class LocmemSmsBackend:
    """Collects messages in memory (used by tests)."""

    outbox: list = []

    def send(self, phone: str, text: str) -> None:
        self.outbox.append((phone, text))
