"""Private S3-compatible receipt storage. Credentials stay on the backend."""

from __future__ import annotations

import hashlib
import os
import uuid

import boto3
from botocore.config import Config


def configured() -> bool:
    names = ("HP_RECEIPT_S3_BUCKET", "HP_RECEIPT_S3_ENDPOINT", "HP_RECEIPT_S3_ACCESS_KEY_ID", "HP_RECEIPT_S3_SECRET_ACCESS_KEY")
    values = [os.environ.get(name, "").strip() for name in names]
    if any(values) and not all(values):
        raise RuntimeError("Incomplete private receipt storage configuration")
    return all(values)


def _client():
    if not configured():
        raise RuntimeError("Private receipt storage is not configured")
    endpoint = os.environ["HP_RECEIPT_S3_ENDPOINT"].strip()
    if not endpoint.startswith("https://"):
        raise RuntimeError("Receipt storage requires HTTPS")
    return boto3.client(
        "s3", endpoint_url=endpoint,
        region_name=os.environ.get("HP_RECEIPT_S3_REGION", "auto"),
        aws_access_key_id=os.environ["HP_RECEIPT_S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["HP_RECEIPT_S3_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=30,
                      retries={"max_attempts": 3, "mode": "standard"},
                      request_checksum_calculation="when_required",
                      response_checksum_validation="when_required",
                      s3={"addressing_style": "virtual"}),
    )


def upload(data: bytes, content_type: str) -> dict:
    key = f"receipts/{uuid.uuid4().hex}"
    digest = hashlib.sha256(data).hexdigest()
    client = _client()
    bucket = os.environ["HP_RECEIPT_S3_BUCKET"].strip()
    client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type,
                      Metadata={"sha256": digest})
    metadata = {"object_key": key, "object_bucket": bucket, "sha256": digest}
    # Verify actual bytes before replacing any database-backed receipt.
    if read(metadata) != data:
        raise RuntimeError("Receipt upload verification failed")
    return metadata


def read(row: dict) -> bytes:
    response = _client().get_object(Bucket=row["object_bucket"], Key=row["object_key"])
    body = response["Body"]
    try:
        data = body.read(2_500_001)
    finally:
        body.close()
    if len(data) > 2_500_000 or hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise RuntimeError("Receipt integrity verification failed")
    return data
