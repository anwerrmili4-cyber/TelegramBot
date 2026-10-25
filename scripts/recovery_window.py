"""Local window that shows whether today's Railway recovery copy finished."""

import json
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.recovery_sync import PROJECT_ROOT, RECOVERY_ROOT, status_snapshot

HOST = "127.0.0.1"
PORT = 8765
_sync_process: subprocess.Popen | None = None
_sync_lock = threading.Lock()

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recovery</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    background: #101114;
    color: #f2f3f5;
    font: 16px/1.45 "Segoe UI", sans-serif;
  }
  main {
    max-width: 640px;
    margin: 0 auto;
    padding: 48px 20px 64px;
  }
  h1 { font-size: 28px; font-weight: 650; margin: 0 0 8px; }
  .lead { color: #b7bdc7; margin: 0 0 28px; }
  .card {
    background: #181b20;
    border: 1px solid #2c323b;
    border-radius: 16px;
    padding: 24px;
  }
  .status {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
  }
  .mark {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #c9842a;
    flex: none;
  }
  .mark.done { background: #3dbe7a; }
  .mark.running { background: #7aa2f7; }
  .status strong { font-size: 20px; }
  .when { color: #b7bdc7; margin: 4px 0 0; }
  .stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin: 8px 0 22px;
  }
  .stat {
    background: #101114;
    border-radius: 12px;
    padding: 14px;
  }
  .stat span { display: block; color: #8d96a3; font-size: 13px; }
  .stat strong { font-size: 22px; font-weight: 650; }
  .actions { display: flex; gap: 10px; flex-wrap: wrap; }
  button {
    font: inherit;
    border: 0;
    border-radius: 10px;
    padding: 10px 16px;
    cursor: pointer;
  }
  button.primary { background: #f2f3f5; color: #101114; }
  button.secondary { background: transparent; color: #f2f3f5; border: 1px solid #3a424e; }
  button:disabled { opacity: 0.55; cursor: default; }
  .note { color: #8d96a3; margin: 18px 0 0; font-size: 14px; }
  @media (max-width: 560px) { .stats { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<main>
  <h1>Database recovery</h1>
  <p class="lead">Copy of the Railway database on this PC.</p>
  <section class="card" aria-live="polite">
    <div class="status">
      <span id="mark" class="mark"></span>
      <div>
        <strong id="headline">Checking</strong>
        <p id="when" class="when"></p>
      </div>
    </div>
    <div class="stats">
      <div class="stat"><span>Database</span><strong id="database">—</strong></div>
      <div class="stat"><span>Collections</span><strong id="collections">—</strong></div>
      <div class="stat"><span>Documents</span><strong id="documents">—</strong></div>
    </div>
    <div class="actions">
      <button class="primary" id="copy" type="button">Copy now</button>
      <button class="secondary" id="folder" type="button">Open archive</button>
    </div>
    <p id="note" class="note"></p>
  </section>
</main>
<script>
const headline = document.getElementById("headline");
const when = document.getElementById("when");
const mark = document.getElementById("mark");
const database = document.getElementById("database");
const collections = document.getElementById("collections");
const documents = document.getElementById("documents");
const note = document.getElementById("note");
const copy = document.getElementById("copy");

function formatWhen(value) {
  if (!value) return "No copy yet";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function render(status) {
  mark.className = "mark" + (status.running ? " running" : status.synced_today ? " done" : "");
  if (status.running) headline.textContent = "Copy in progress";
  else if (status.synced_today) headline.textContent = "Done today";
  else headline.textContent = "Not done today";
  when.textContent = status.running ? "Started " + formatWhen(status.started) : "Last finished " + formatWhen(status.finished);
  database.textContent = (status.databases && status.databases[0]) || "—";
  collections.textContent = status.collections ?? "—";
  documents.textContent = (status.documents ?? 0).toLocaleString();
  const local = status.local_database ? "Local database updated." : "Archive saved. Local database was not running.";
  note.textContent = local + " Next try is " + status.next_run + ". If the PC is off then, the copy runs the next time you log in.";
  copy.disabled = Boolean(status.running);
  copy.textContent = status.running ? "Copying…" : "Copy now";
}

async function refresh() {
  const response = await fetch("/api/status");
  render(await response.json());
}

copy.addEventListener("click", async () => {
  copy.disabled = true;
  copy.textContent = "Copying…";
  await fetch("/api/sync", { method: "POST" });
  refresh();
});

document.getElementById("folder").addEventListener("click", () => {
  fetch("/api/open-folder", { method: "POST" });
});

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


def _sync_running() -> bool:
    with _sync_lock:
        return _sync_process is not None and _sync_process.poll() is None


def _start_sync() -> None:
    global _sync_process
    with _sync_lock:
        if _sync_process is not None and _sync_process.poll() is None:
            return
        script = PROJECT_ROOT / "scripts" / "sync_recovery_db.py"
        _sync_process = subprocess.Popen(
            [sys.executable, str(script), "--force"],
            cwd=str(PROJECT_ROOT),
        )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            payload = status_snapshot()
            payload["running"] = payload["running"] or _sync_running()
            self._send(200, json.dumps(payload).encode(), "application/json")
            return
        if path in {"/", "/index.html"}:
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/sync":
            _start_sync()
            self._send(202, b'{"ok":true}', "application/json")
            return
        if path == "/api/open-folder":
            RECOVERY_ROOT.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(["explorer", str(RECOVERY_ROOT)])
            self._send(202, b'{"ok":true}', "application/json")
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    print(f"Recovery window: {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
