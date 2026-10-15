"""Open the fournisseurs page in the local admin.

Starts only the admin site on 127.0.0.1:8081. It does not register the
Telegram webhook and does not start the public bot.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = 8081
URL = f"http://{HOST}:{PORT}/admin/api-products"


def _port_open() -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((HOST, PORT)) == 0


def _start_admin() -> None:
    flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.web.admin_app:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ],
        cwd=ROOT,
        creationflags=flags,
    )


def main() -> None:
    if not _port_open():
        _start_admin()
        for _ in range(40):
            if _port_open():
                break
            time.sleep(0.25)
    if not _port_open():
        print("L’administration n’a pas démarré. Regardez la fenêtre du serveur.")
        return
    webbrowser.open(URL)


if __name__ == "__main__":
    main()
