import base64
import hashlib
import io

import pytest

from app.domain import receipt_object_storage as storage
from app.domain import storefront_receipt_service as receipts

IMAGE = b"\x89PNG\r\n\x1a\n" + b"test image"
UPLOAD = "data:image/png;base64," + base64.b64encode(IMAGE).decode()


@pytest.fixture
def private_bucket(monkeypatch):
    for name, value in {
        "BUCKET": "private-receipts", "ENDPOINT": "https://storage.example.com",
        "ACCESS_KEY_ID": "test-key", "SECRET_ACCESS_KEY": "test-secret",
    }.items():
        monkeypatch.setenv("HP_RECEIPT_S3_" + name, value)
    objects = {}

    class Client:
        def put_object(self, **kwargs):
            assert "ACL" not in kwargs
            objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]

        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(objects[(kwargs["Bucket"], kwargs["Key"])])}

    monkeypatch.setattr(storage, "_client", lambda: Client())
    return objects


def test_private_upload_roundtrip_without_database_blob(private_bucket, mock_mongodb):
    receipt_id = receipts.store(UPLOAD, customer_id=4, purpose="warranty")
    row = mock_mongodb.storefront_receipts.find_one({"id": receipt_id})
    assert "data" not in row
    assert row["customer_id"] == 4
    assert row["sha256"] == hashlib.sha256(IMAGE).hexdigest()
    assert receipts.load(receipt_id) == (IMAGE, "image/png")


def test_corrupted_object_is_rejected(private_bucket):
    metadata = storage.upload(IMAGE, "image/png")
    private_bucket[(metadata["object_bucket"], metadata["object_key"])] = b"corrupt"
    with pytest.raises(RuntimeError, match="integrity"):
        storage.read(metadata)


def test_failed_upload_does_not_save_receipt(private_bucket, mock_mongodb, monkeypatch):
    def fail(*args):
        raise RuntimeError("storage unavailable")
    monkeypatch.setattr(storage, "upload", fail)
    with pytest.raises(RuntimeError):
        receipts.store(UPLOAD, customer_id=4, purpose="order")
    assert mock_mongodb.storefront_receipts.count_documents({}) == 0


def test_legacy_receipt_remains_readable(mock_mongodb):
    mock_mongodb.storefront_receipts.insert_one({"id": 9, "data": IMAGE, "content_type": "image/png"})
    assert receipts.load(9) == (IMAGE, "image/png")


def test_partial_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("HP_RECEIPT_S3_BUCKET", "private-receipts")
    with pytest.raises(RuntimeError, match="Incomplete"):
        storage.configured()
