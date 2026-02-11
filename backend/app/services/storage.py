"""File storage service — local filesystem or S3."""

import os
import uuid
from pathlib import Path
from app.core.config import settings


async def save_pdf(filename: str, content: bytes) -> str:
    """Save PDF bytes and return a storage key."""
    if settings.storage_backend == "local":
        return await _save_local(filename, content)
    else:
        return await _save_s3(filename, content)


async def get_pdf_path(storage_key: str) -> str:
    """Get the local file path for a stored PDF."""
    if settings.storage_backend == "local":
        return os.path.join(settings.local_storage_path, storage_key)
    else:
        # For S3, download to temp and return temp path
        return await _download_s3(storage_key)


async def _save_local(filename: str, content: bytes) -> str:
    base_dir = Path(settings.local_storage_path)
    base_dir.mkdir(parents=True, exist_ok=True)
    key = f"{uuid.uuid4().hex}_{filename}"
    filepath = base_dir / key
    filepath.write_bytes(content)
    return key


async def _save_s3(filename: str, content: bytes) -> str:
    import boto3
    s3 = boto3.client(
        "s3",
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )
    key = f"pdfs/{uuid.uuid4().hex}_{filename}"
    s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=content)
    return key


async def _download_s3(storage_key: str) -> str:
    import boto3
    import tempfile
    s3 = boto3.client(
        "s3",
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    s3.download_file(settings.s3_bucket, storage_key, tmp.name)
    return tmp.name
