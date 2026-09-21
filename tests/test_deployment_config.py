"""Railway safeguards for services with region-sensitive upstream APIs."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_railway_runs_single_webhook_replica_in_europe():
    config = json.loads((PROJECT_ROOT / "railway.json").read_text(encoding="utf-8"))

    assert config["build"] == {
        "builder": "DOCKERFILE",
        "dockerfilePath": "Dockerfile",
    }
    deploy = config["deploy"]
    assert deploy["startCommand"] == "python railway_server.py"
    assert deploy["healthcheckPath"] == "/health"
    assert deploy["multiRegionConfig"] == {
        "europe-west4-drams3a": {"numReplicas": 1}
    }


def test_railway_docker_image_uses_supported_python_and_non_root_user():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim\n" in dockerfile
    assert "FROM node:24-slim AS admin-build" in dockerfile
    assert "RUN npm ci" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert "COPY --from=admin-build --chown=appuser:appuser /build/admin-ui/dist ./admin-ui/dist" in dockerfile
    assert "pip install --no-cache-dir --requirement requirements.txt" in dockerfile
    assert "USER appuser" in dockerfile
    assert 'CMD ["python", "railway_server.py"]' in dockerfile


def test_admin_catalog_declares_delete_confirmation_state():
    source = (PROJECT_ROOT / "admin-ui" / "src" / "AdminPages.jsx").read_text(
        encoding="utf-8"
    )

    assert "const [deleteTarget, setDeleteTarget] = useState(null);" in source


def test_offer_editor_does_not_reference_removed_image_upload_state():
    source = (PROJECT_ROOT / "admin-ui" / "src" / "AdminPages.jsx").read_text(
        encoding="utf-8"
    )

    assert "imageBusy" not in source
    assert "portraitBusy" not in source


def test_react_admin_sends_scoped_token_for_write_requests():
    app_source = (PROJECT_ROOT / "admin-ui" / "src" / "App.jsx").read_text(
        encoding="utf-8"
    )
    pages_source = (
        PROJECT_ROOT / "admin-ui" / "src" / "AdminPages.jsx"
    ).read_text(encoding="utf-8")

    expected_header = '"X-Dashboard-Write-Token"'
    assert expected_header in app_source
    assert expected_header in pages_source
