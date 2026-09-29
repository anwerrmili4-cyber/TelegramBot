"""Configuration et fixtures globales pour pytest."""

from __future__ import annotations

import base64
import time

import mongomock
import pytest

import database

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
