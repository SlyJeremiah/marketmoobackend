import re

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import storage
from .models import Pack


class ManifestView(APIView):
    """Tiny, cacheable list of the newest pack per district (size and checksum so the app can resume and verify)."""
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        qs = Pack.objects.all()
        district = request.query_params.get("district")
        if district:
            qs = qs.filter(district__iexact=district)
        newest = {}
        for p in qs:
            key = (p.district, p.kind)
            if key not in newest or p.version > newest[key].version:
                newest[key] = p
        items = [
            {"district": p.district, "kind": p.kind, "version": p.version, "size_bytes": p.size_bytes, "sha256": p.sha256,
             "url": storage.presigned_get(p.storage_key, p.filename) if (p.storage_key and storage.enabled()) else request.build_absolute_uri(f"/v1/packs/{p.pk}/download"),
             "note": p.data_note}
            for p in newest.values()
        ]
        resp = Response({"packs": items})
        resp["Cache-Control"] = "private, max-age=60"  # presigned URLs expire, so do not cache for long
        return resp


class DownloadView(APIView):
    """Dev download with HTTP Range support (resumable). In production packs are served by Cloudflare R2 instead."""
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, pk):
        pack = Pack.objects.filter(pk=pk).first()
        if pack is None:
            raise Http404
        path = (settings.PACK_DIR / pack.filename).resolve()
        if settings.PACK_DIR.resolve() not in path.parents or not path.exists():
            raise Http404
        size = path.stat().st_size
        rng = request.headers.get("Range", "")
        m = re.match(r"bytes=(\d*)-(\d*)$", rng)
        if m and (m.group(1) or m.group(2)):
            start = int(m.group(1)) if m.group(1) else max(size - int(m.group(2)), 0)
            end = int(m.group(2)) if m.group(1) and m.group(2) else size - 1
            end = min(end, size - 1)
            if start > end or start >= size:
                return HttpResponse(status=416, headers={"Content-Range": f"bytes */{size}"})
            with open(path, "rb") as f:
                f.seek(start)
                data = f.read(end - start + 1)
            resp = HttpResponse(data, status=206, content_type="application/octet-stream")
            resp["Content-Range"] = f"bytes {start}-{end}/{size}"
            resp["Content-Length"] = str(len(data))
            resp["Accept-Ranges"] = "bytes"
            return resp
        resp = FileResponse(open(path, "rb"), content_type="application/octet-stream")
        resp["Accept-Ranges"] = "bytes"
        resp["Content-Length"] = str(size)
        return resp
