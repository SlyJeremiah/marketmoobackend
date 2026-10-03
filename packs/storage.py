"""Object storage on Backblaze B2 through its S3-compatible API.

Packs and photos live in the bucket; the API only hands out short-lived presigned URLs, so the bucket can stay
private and the app downloads straight from B2 (HTTP Range works, so large downloads resume).
When no B2 key is configured (local development, tests) every function reports `enabled() == False`
and callers fall back to local disk.
"""
from functools import lru_cache

from django.conf import settings


def enabled() -> bool:
    return bool(settings.B2_KEY_ID and settings.B2_APP_KEY and settings.B2_BUCKET and settings.B2_S3_ENDPOINT)


@lru_cache(maxsize=1)
def client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3", endpoint_url=settings.B2_S3_ENDPOINT, region_name=settings.B2_REGION,
        aws_access_key_id=settings.B2_KEY_ID, aws_secret_access_key=settings.B2_APP_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
    )


def upload_file(path, key, content_type="application/octet-stream"):
    client().upload_file(str(path), settings.B2_BUCKET, key, ExtraArgs={"ContentType": content_type})


def presigned_get(key, filename=None):
    params = {"Bucket": settings.B2_BUCKET, "Key": key}
    if filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    return client().generate_presigned_url("get_object", Params=params, ExpiresIn=settings.B2_URL_TTL)


def presigned_put(key, content_type="image/webp"):
    """URL the phone uploads a photo to directly (the API never proxies image bytes)."""
    return client().generate_presigned_url(
        "put_object", Params={"Bucket": settings.B2_BUCKET, "Key": key, "ContentType": content_type}, ExpiresIn=900)


def exists(key) -> bool:
    from botocore.exceptions import ClientError

    try:
        client().head_object(Bucket=settings.B2_BUCKET, Key=key)
        return True
    except ClientError:
        return False
