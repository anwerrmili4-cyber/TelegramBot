import json
from datetime import date
from pathlib import Path

import pytest
from bson import encode

from app.recovery_sync import (
    finished_on,
    iter_bson,
    prune_old_archives,
    redact,
    summarize_report,
    tunnel_uri,
    user_database_names,
)


def test_summarize_report_counts_documents_without_connection_details():
    summary = summarize_report(
        {
            "finished": "2026-10-15T18:04:43+01:00",
            "archive": "C:/recovery/2026-10-15",
            "local_database": True,
            "databases": {
                "heavenprem": {
                    "collections": {
                        "orders": {"documents": 10},
                        "users": {"documents": 2},
                    }
                }
            },
        },
        date(2026, 10, 15),
    )
    assert summary["synced_today"] is True
    assert summary["collections"] == 2
    assert summary["documents"] == 12
    assert summary["databases"] == ["heavenprem"]
    assert "mongodb://" not in json.dumps(summary)


def test_finished_on_matches_the_local_day():
    assert finished_on({"finished": "2026-10-15T18:05:00+01:00"}, date(2026, 10, 15))
    assert not finished_on({"finished": "2026-10-14T18:05:00+01:00"}, date(2026, 10, 15))
    assert not finished_on({}, date(2026, 10, 15))


def test_user_databases_skip_mongo_system_databases():
    assert user_database_names(["admin", "heavenprem", "local", "config", "shop"]) == [
        "heavenprem",
        "shop",
    ]


def test_redact_hides_mongodb_connection_strings():
    text = "failed mongodb://mongo:secret@127.0.0.1:27018/?authSource=admin now"
    assert "secret" not in redact(text)
    assert "mongodb://***" in redact(text)


def test_tunnel_uri_quotes_special_characters():
    uri = tunnel_uri("mongo", "p@ss/word", 27018)
    assert "p%40ss%2Fword" in uri
    assert "authSource=admin" in uri
    assert uri.startswith("mongodb://mongo:")


def test_iter_bson_reads_concatenated_documents():
    raw = encode({"_id": 1, "name": "a"}) + encode({"_id": 2})
    docs = list(iter_bson(iter([raw[:3], raw[3:]])))
    assert docs == [{"_id": 1, "name": "a"}, {"_id": 2}]


def test_iter_bson_rejects_a_truncated_stream():
    raw = encode({"_id": 1})
    with pytest.raises(ValueError, match="truncated"):
        list(iter_bson(iter([raw[:4]])))


def test_prune_removes_only_dated_folders_outside_the_window(tmp_path: Path):
    old = tmp_path / "2026-09-01"
    fresh = tmp_path / "2026-10-10"
    notes = tmp_path / "notes"
    old.mkdir()
    fresh.mkdir()
    notes.mkdir()

    removed = prune_old_archives(tmp_path, keep_days=14, today=date(2026, 10, 15))

    assert removed == [old]
    assert not old.exists()
    assert fresh.exists()
    assert notes.exists()


def test_dump_and_load_round_trip(tmp_path: Path):
    from app.recovery_sync import dump_collection, load_collection

    class FakeCollection:
        def __init__(self, documents):
            self.documents = documents

        def find(self, batch_size=0):
            return iter(self.documents)

    class FakeDest:
        def __init__(self):
            self.inserted = []

        def insert_many(self, batch, ordered=False):
            self.inserted.extend(batch)

    path = tmp_path / "orders.bson.gz"
    assert dump_collection(FakeCollection([{"_id": 1}, {"_id": 2}]), path) == 2
    dest = FakeDest()
    assert load_collection(path, dest) == 2
    assert dest.inserted == [{"_id": 1}, {"_id": 2}]
