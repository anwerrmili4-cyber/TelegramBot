"""Configuration et fixtures globales pour pytest."""

from __future__ import annotations

import mongomock
import pytest

import database


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
