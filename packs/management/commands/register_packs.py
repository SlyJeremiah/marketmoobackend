import hashlib
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from packs import storage
from packs.models import Pack


class Command(BaseCommand):
    help = "Copy pack_<District>.sqlite files from the GIS pipeline into PACK_DIR and register them (size and sha256)."

    def add_arguments(self, parser):
        parser.add_argument("source", help="Folder containing pack_<District>.sqlite (for example build/results/packs)")
        parser.add_argument("--pack-version", default="2026.10.02")

    def handle(self, *args, **opts):
        src = Path(opts["source"])
        settings.PACK_DIR.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in sorted(src.glob("pack_*.sqlite")):
            district = re.sub(r"^pack_|\.sqlite$", "", f.name)
            dest = settings.PACK_DIR / f"{district}-{opts['pack_version']}.sqlite"
            shutil.copy2(f, dest)
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            key = ""
            if storage.enabled():
                key = f"packs/{dest.name}"
                storage.upload_file(dest, key)
                self.stdout.write(f"uploaded {key} to the B2 bucket")
            Pack.objects.update_or_create(
                district=district, kind="lookup", version=opts["pack_version"],
                defaults=dict(filename=dest.name, size_bytes=dest.stat().st_size, sha256=digest, storage_key=key,
                              data_note="School-trial pack built from open data (see Design Document, Section 7)."),
            )
            n += 1
            self.stdout.write(f"registered {district} {opts['pack_version']} ({dest.stat().st_size // 1024} KB)")
        self.stdout.write(self.style.SUCCESS(f"{n} pack(s) registered"))
