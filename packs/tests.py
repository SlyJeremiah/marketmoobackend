import hashlib
import sqlite3
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


class PackTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        src = self.tmp / "src"
        src.mkdir()
        db = sqlite3.connect(src / "pack_Gwanda.sqlite")
        db.execute("create table meta(k text, v text)")
        db.executemany("insert into meta values(?,?)", [("filler", "x" * 5000)])
        db.commit()
        db.close()
        self.override = override_settings(PACK_DIR=self.tmp / "packs")
        self.override.enable()
        call_command("register_packs", str(src), "--pack-version", "t1", verbosity=0)
        self.c = APIClient()

    def tearDown(self):
        self.override.disable()

    def test_manifest_has_size_and_checksum(self):
        p = self.c.get("/v1/packs/manifest", {"district": "gwanda"}).json()["packs"][0]
        data = (self.tmp / "packs" / "Gwanda-t1.sqlite").read_bytes()
        self.assertEqual(p["size_bytes"], len(data))
        self.assertEqual(p["sha256"], hashlib.sha256(data).hexdigest())

    def test_download_supports_resume(self):
        url = self.c.get("/v1/packs/manifest").json()["packs"][0]["url"].replace("http://testserver", "")
        full = b"".join(self.c.get(url).streaming_content)
        part = self.c.get(url, HTTP_RANGE="bytes=100-199")
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part.content, full[100:200])
        self.assertEqual(part["Content-Range"], f"bytes 100-199/{len(full)}")
        tail = self.c.get(url, HTTP_RANGE="bytes=-50")
        self.assertEqual(tail.content, full[-50:])
        self.assertEqual(self.c.get(url, HTTP_RANGE=f"bytes={len(full) + 10}-").status_code, 416)

    def test_unknown_pack_is_404(self):
        self.assertEqual(self.c.get("/v1/packs/9999/download").status_code, 404)


class PingTests(TestCase):
    def test_ping_is_one_byte(self):
        r = APIClient().get("/v1/ping")
        self.assertEqual(r.content, b"1")
