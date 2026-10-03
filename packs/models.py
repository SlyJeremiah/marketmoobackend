from django.db import models


class Pack(models.Model):
    """A downloadable per-district data pack produced by the GIS pipeline (SQLite file)."""

    district = models.CharField(max_length=40)
    kind = models.CharField(max_length=20, default="lookup")
    version = models.CharField(max_length=20)
    filename = models.CharField(max_length=120)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    data_note = models.CharField(max_length=300, blank=True)
    storage_key = models.CharField(max_length=200, blank=True, help_text="Object key in the B2 bucket; empty = local file.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("district", "kind", "version")]
        ordering = ["district", "-version"]

    def __str__(self):
        return f"{self.district} {self.kind} {self.version}"
