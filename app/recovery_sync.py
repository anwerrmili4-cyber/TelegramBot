"""Daily copy of the Railway MongoDB databases onto this PC.

The Railway database is on a private network. Each run opens a Railway tunnel,
writes a dated archive under ``data/recovery/``, and, when a local MongoDB is
listening, replaces the local recovery copy one collection at a time.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

from bson import decode, encode, json_util
from pymongo import MongoClient
from pymongo.errors import PyMongoError

SYSTEM_DATABASES = frozenset({"admin", "local", "config"})
ARCHIVE_DAYS = 14
BATCH_SIZE = 500
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECOVERY_ROOT = PROJECT_ROOT / "data" / "recovery"
TASK_NAME = "BlackMarket Mongo recovery"
_URI_RE = re.compile(r"mongodb(?:\+srv)?://\S+", re.IGNORECASE)


def redact(text: str) -> str:
    """Remove connection strings from text that may be written to a log."""
    return _URI_RE.sub("mongodb://***", text)


def user_database_names(names: list[str]) -> list[str]:
    return sorted(name for name in names if name not in SYSTEM_DATABASES)


def archive_dir(day: date | None = None) -> Path:
    stamp = (day or date.today()).isoformat()
    return RECOVERY_ROOT / stamp


def prune_old_archives(root: Path, *, keep_days: int = ARCHIVE_DAYS, today: date | None = None) -> list[Path]:
    """Delete dated archive folders older than the retention window."""
    cutoff = (today or date.today()) - timedelta(days=keep_days)
    removed: list[Path] = []
    if not root.exists():
        return removed
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            folder_day = date.fromisoformat(child.name)
        except ValueError:
            continue
        if folder_day < cutoff:
            shutil.rmtree(child)
            removed.append(child)
    return removed


def tunnel_uri(user: str, password: str, port: int) -> str:
    return remote_uri(user, password, "127.0.0.1", port)


def remote_uri(user: str, password: str, host: str, port: int) -> str:
    return (
        f"mongodb://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/?authSource=admin&directConnection=true"
    )


def iter_bson(chunks: Iterator[bytes]) -> Iterator[dict]:
    """Yield documents from a stream of concatenated BSON bytes."""
    buf = b""
    for chunk in chunks:
        buf += chunk
        while len(buf) >= 4:
            size = int.from_bytes(buf[:4], "little")
            if size < 5 or size > 16_777_216:
                raise ValueError(f"invalid BSON document size {size}")
            if len(buf) < size:
                break
            yield decode(buf[:size])
            buf = buf[size:]
    if buf:
        raise ValueError("truncated BSON stream")


def dump_collection(collection, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with gzip.open(path, "wb") as handle:
        for document in collection.find(batch_size=BATCH_SIZE):
            handle.write(encode(document))
            count += 1
    return count


def load_collection(path: Path, collection) -> int:
    count = 0
    batch: list[dict] = []

    def flush() -> None:
        nonlocal count
        if not batch:
            return
        collection.insert_many(batch, ordered=False)
        count += len(batch)
        batch.clear()

    with gzip.open(path, "rb") as handle:
        def chunks() -> Iterator[bytes]:
            while True:
                block = handle.read(256 * 1024)
                if not block:
                    break
                yield block

        for document in iter_bson(chunks()):
            batch.append(document)
            if len(batch) >= BATCH_SIZE:
                flush()
    flush()
    return count


def index_specs(collection) -> list[dict]:
    specs = []
    for spec in collection.list_indexes():
        if spec.get("name") == "_id_":
            continue
        specs.append(json.loads(json_util.dumps(spec)))
    return specs


def create_indexes(collection, specs: list[dict]) -> None:
    for spec in specs:
        keys = spec["key"]
        if isinstance(keys, dict):
            keys = list(keys.items())
        options = {
            field: spec[field]
            for field in ("unique", "sparse", "expireAfterSeconds", "partialFilterExpression", "collation")
            if field in spec
        }
        collection.create_index(keys, name=spec["name"], **options)


def replace_collection(database, name: str, path: Path, specs: list[dict]) -> int:
    """Load a dump beside the live collection, then swap the names."""
    incoming = f"{name}__incoming"
    if incoming in database.list_collection_names():
        database[incoming].drop()
    count = load_collection(path, database[incoming])
    if incoming not in database.list_collection_names():
        database.create_collection(incoming)
    create_indexes(database[incoming], specs)
    if name in database.list_collection_names():
        database[name].drop()
    database[incoming].rename(name)
    return count


def railway_executable() -> str:
    found = shutil.which("railway")
    if not found:
        raise RuntimeError("The Railway CLI is not installed or not on PATH.")
    cmd = Path(found).with_suffix(".cmd")
    if os.name == "nt" and cmd.exists():
        return str(cmd)
    return found


def railway_proxy(railway_bin: str) -> tuple[str, int] | None:
    """Return the public host and port for the Railway MongoDB service, if one exists."""
    completed = subprocess.run(
        [railway_bin, "tcp-proxy", "list", "--service", "MongoDB", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    proxies = json.loads(completed.stdout).get("proxies") or []
    if not proxies:
        return None
    proxy = proxies[0]
    domain = str(proxy.get("domain") or "").strip()
    port = proxy.get("proxyPort")
    if not domain or not port:
        return None
    return domain, int(port)


def mongo_credentials(railway_bin: str) -> tuple[str, str]:
    completed = subprocess.run(
        [railway_bin, "variable", "list", "--service", "MongoDB", "--json"],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    if completed.returncode != 0:
        detail = redact(completed.stderr or completed.stdout or "Railway CLI failed")
        raise RuntimeError(detail.strip() or "Could not read the Railway MongoDB service.")
    payload = json.loads(completed.stdout)
    user = str(payload.get("MONGOUSER") or "").strip()
    password = str(payload.get("MONGOPASSWORD") or "")
    if not user or not password:
        raise RuntimeError("Railway MongoDB credentials are missing.")
    return user, password


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


class RailwayTunnel:
    """Local tunnel to the private Railway MongoDB. Closed when the copy finishes."""

    def __init__(self, railway_bin: str, port: int = 27018) -> None:
        self.railway_bin = railway_bin
        self.port = port
        self.process: subprocess.Popen | None = None

    def __enter__(self) -> int:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.process = subprocess.Popen(
            ["cmd", "/c", self.railway_bin, "connect", "MongoDB", "--tunnel-only", "--port", str(self.port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("The Railway tunnel stopped before MongoDB was reachable.")
            if _port_open(self.port):
                return self.port
            time.sleep(0.4)
        raise RuntimeError("The Railway tunnel did not open within 60 seconds.")

    def __exit__(self, exc_type, exc, tb) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )
        else:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def sync_database(source, destination_client, database_name: str, folder: Path) -> dict:
    """Archive one database and refresh the local copy when a destination exists."""
    folder.mkdir(parents=True, exist_ok=True)
    summary: dict = {"collections": {}}
    listed = list(source.list_collections())
    for info in listed:
        name = info["name"]
        if name.startswith("system."):
            continue
        entry: dict = {"type": info.get("type", "collection")}
        if entry["type"] == "view":
            entry["options"] = json.loads(json_util.dumps(info.get("options") or {}))
            summary["collections"][name] = entry
            if destination_client is not None:
                _restore_view(destination_client[database_name], name, entry["options"])
            continue
        bson_path = folder / f"{name}.bson.gz"
        specs = index_specs(source[name])
        entry["documents"] = dump_collection(source[name], bson_path)
        entry["indexes"] = len(specs)
        (folder / f"{name}.indexes.json").write_text(json_util.dumps(specs), encoding="utf-8")
        if destination_client is not None:
            entry["local_documents"] = replace_collection(
                destination_client[database_name], name, bson_path, specs
            )
        summary["collections"][name] = entry
    (folder / "collections.json").write_text(json_util.dumps(summary), encoding="utf-8")
    return summary


def _restore_view(database, name: str, options: dict) -> None:
    if name in database.list_collection_names():
        database[name].drop()
    database.command({
        "create": name,
        "viewOn": options.get("viewOn"),
        "pipeline": options.get("pipeline") or [],
    })


@contextmanager
def _direct_source(uri: str):
    client = MongoClient(uri, serverSelectionTimeoutMS=20_000, directConnection=True)
    try:
        client.admin.command("ping")
        yield client
    finally:
        client.close()


@contextmanager
def _tunnel_source(railway_bin: str, user: str, password: str, port: int):
    with (
        RailwayTunnel(railway_bin, port) as tunnel_port,
        _direct_source(tunnel_uri(user, password, tunnel_port)) as client,
    ):
        yield client


def local_client(uri: str) -> MongoClient | None:
    client = MongoClient(uri, serverSelectionTimeoutMS=2_000, directConnection=True)
    try:
        client.admin.command("ping")
    except PyMongoError:
        client.close()
        return None
    return client


def run_sync(*, port: int = 27018, local_uri: str | None = None) -> dict:
    railway_bin = railway_executable()
    user, password = mongo_credentials(railway_bin)
    destination_uri = local_uri or os.environ.get("HP_LOCAL_MONGODB_URI", "mongodb://127.0.0.1:27017")
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    folder = archive_dir()
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    RECOVERY_ROOT.mkdir(parents=True, exist_ok=True)
    (RECOVERY_ROOT / "running.json").write_text(
        json.dumps({"started": started}),
        encoding="utf-8",
    )
    report: dict = {"started": started, "archive": str(folder), "databases": {}}
    try:
        proxy = railway_proxy(railway_bin)
        if proxy is None:
            source_cm = _tunnel_source(railway_bin, user, password, port)
        else:
            host, proxy_port = proxy
            source_cm = _direct_source(remote_uri(user, password, host, proxy_port))
        with source_cm as source:
            destination = local_client(destination_uri)
            report["local_database"] = destination is not None
            try:
                names = user_database_names(source.list_database_names())
                if not names:
                    raise RuntimeError("The Railway MongoDB has no user databases to copy.")
                for name in names:
                    report["databases"][name] = sync_database(
                        source[name], destination, name, folder / name
                    )
            finally:
                if destination is not None:
                    destination.close()
        report["finished"] = datetime.now().astimezone().isoformat(timespec="seconds")
        removed = prune_old_archives(RECOVERY_ROOT)
        report["removed_archives"] = [path.name for path in removed]
        (folder / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (RECOVERY_ROOT / "last-sync.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        (RECOVERY_ROOT / "running.json").unlink(missing_ok=True)


def finished_on(report: dict, day: date) -> bool:
    return str(report.get("finished") or "").startswith(day.isoformat())


def summarize_report(report: dict, day: date) -> dict:
    """Return the fields the status window shows. No connection strings."""
    databases = report.get("databases") or {}
    collections = 0
    documents = 0
    for database in databases.values():
        for entry in (database.get("collections") or {}).values():
            collections += 1
            documents += int(entry.get("documents") or 0)
    return {
        "synced_today": finished_on(report, day),
        "finished": report.get("finished"),
        "started": report.get("started"),
        "archive": report.get("archive"),
        "local_database": bool(report.get("local_database")),
        "databases": list(databases),
        "collections": collections,
        "documents": documents,
    }


def status_snapshot(day: date | None = None) -> dict:
    today = day or date.today()
    path = RECOVERY_ROOT / "last-sync.json"
    report: dict = {}
    if path.exists():
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
    summary = summarize_report(report, today)
    running_path = RECOVERY_ROOT / "running.json"
    summary["running"] = running_path.exists()
    if summary["running"]:
        try:
            running = json.loads(running_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            running = {}
        summary["started"] = running.get("started") or summary["started"]
    summary["next_run"] = "04:00"
    return summary


def synced_today() -> bool:
    path = RECOVERY_ROOT / "last-sync.json"
    if not path.exists():
        return False
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return finished_on(report, date.today())


def install_daily_task() -> str:
    """Register a 04:00 task that also runs after a missed start once the PC is on."""
    runner = PROJECT_ROOT / "scripts" / "run_recovery_sync.cmd"
    if not runner.exists():
        raise RuntimeError(f"Missing task runner: {runner}")
    completed = subprocess.run(
        [
            "schtasks",
            "/Create",
            "/F",
            "/TN",
            TASK_NAME,
            "/SC",
            "DAILY",
            "/ST",
            "04:00",
            "/TR",
            str(runner),
            "/RL",
            "LIMITED",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "schtasks failed").strip()
        raise RuntimeError(detail)
    enable_catch_up = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "$task = Get-ScheduledTask -TaskName 'BlackMarket Mongo recovery'; "
                "$task.Settings.StartWhenAvailable = $true; "
                "Set-ScheduledTask -InputObject $task | Out-Null"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if enable_catch_up.returncode != 0:
        detail = (enable_catch_up.stderr or enable_catch_up.stdout or "Could not enable catch-up").strip()
        raise RuntimeError(detail)
    return TASK_NAME


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    try:
        if "--install-task" in args:
            name = install_daily_task()
            print(f"Daily recovery task registered: {name} at 04:00, with catch-up when the PC is on")
            return 0
        if "--force" not in args and synced_today():
            print("Recovery copy already finished today.")
            return 0
        report = run_sync()
    except (OSError, RuntimeError, PyMongoError, ValueError, json.JSONDecodeError) as exc:
        print(redact(str(exc)), file=sys.stderr)
        return 1
    databases = ", ".join(report["databases"]) or "none"
    where = "and into local MongoDB" if report["local_database"] else "as files only; local MongoDB is not running"
    print(f"Recovery copy saved to {report['archive']} ({databases}) {where}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
