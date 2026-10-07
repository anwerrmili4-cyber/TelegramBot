"""Configuration et fixtures globales pour pytest."""

from __future__ import annotations

import base64
import time

import mongomock
import mongomock.collection
import pytest

import database

# pymongo 4.11+ passes ``sort`` to bulk UpdateOne; mongomock 4.3 predates it.
_mongomock_add_update = mongomock.collection.BulkOperationBuilder.add_update
if "sort" not in _mongomock_add_update.__code__.co_varnames:
    def _add_update_ignoring_sort(self, *args, sort=None, **kwargs):
        return _mongomock_add_update(self, *args, **kwargs)

    mongomock.collection.BulkOperationBuilder.add_update = _add_update_ignoring_sort

RECEIPT = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()


@pytest.fixture(autouse=True)
def mock_mongodb(monkeypatch):
    """Mock process-wide MongoDB connection for tests."""
    client = mongomock.MongoClient()
    db = client["heavenprem"]

    # Remplacer les variables globales dans database.py
    from cryptography.fernet import Fernet
    monkeypatch.setattr(database, "INVENTORY_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(database, "_client", client)
    monkeypatch.setattr(database, "_db", db)
    monkeypatch.setattr(database, "_schema_initialized", False)

    # Initialiser les index et collections simulés
    database.init_db()

    return db


@pytest.fixture(autouse=True)
def deterministic_runtime(monkeypatch):
    """mongomock bypasses the driver's write listener, so tests read live data.

    Supplier refreshes also run inline so no thread outlives its test.
    """
    from app.bot import middlewares
    from app.core.cache import cache
    from app.domain import reseller_service, storefront_service

    cache.clear()
    monkeypatch.setattr(storefront_service, "CATALOG_CACHE_SECONDS", 0)
    monkeypatch.setattr(middlewares, "GUARD_CACHE_SECONDS", 0)
    monkeypatch.setattr(reseller_service, "SUPPLIER_REFRESH_IN_BACKGROUND", False)
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def sent_emails(monkeypatch):
    """Capture Resend messages instead of posting them."""
    from app.domain import email_service

    sent: list[dict] = []
    monkeypatch.setattr(email_service, "_dispatch", sent.append)
    return sent


@pytest.fixture
def site_customer(mock_mongodb):
    """Factory for verified storefront accounts."""

    def create(name="Amine Ben Salah", email="amine@example.com", phone="+21621111222"):
        customer = {
            "id": database._next_id("storefront_customers"),
            "name": name,
            "email": email,
            "phone": phone,
            "email_verified": True,
            "created_at": int(time.time()),
        }
        mock_mongodb.storefront_customers.insert_one(dict(customer))
        return customer

    return create
