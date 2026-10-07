"""Typed runtime settings for the HTTP servers, the scheduler and the job runner.

Business settings (bot token, payment providers, suppliers) stay in the
top-level :mod:`config` module; this object only groups what the server
process needs to start, validated once at boot.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import config

_TELEGRAM_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


def _int_env(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    return max(minimum, value)


@dataclass(frozen=True)
class ScheduleSettings:
    restock_seconds: int = 300
    prices_seconds: int = 600
    pending_payments_seconds: int = 30
    codex_deadlines_seconds: int = 15

    @classmethod
    def from_env(cls) -> ScheduleSettings:
        return cls(
            restock_seconds=_int_env("HP_RESTOCK_INTERVAL_SECONDS", 300, 60),
            prices_seconds=_int_env("HP_PRICE_INTERVAL_SECONDS", 600, 60),
            pending_payments_seconds=_int_env("HP_PENDING_PAYMENT_MONITOR_INTERVAL_SECONDS", 30, 10),
            codex_deadlines_seconds=_int_env("HP_CODEX_MONITOR_INTERVAL_SECONDS", 15, 10),
        )


@dataclass(frozen=True)
class RuntimeSettings:
    port: int = 8080
    admin_port: int = 8081
    storefront_port: int = 8082
    webhook_secret: str = ""
    cron_secret: str = ""
    public_base_url: str = ""
    job_concurrency: int = 4
    schedule: ScheduleSettings = field(default_factory=ScheduleSettings)

    @classmethod
    def from_env(cls) -> RuntimeSettings:
        try:
            port = int(os.environ.get("PORT", "8080"))
            admin_port = int(os.environ.get("ADMIN_PORT", "8081"))
            storefront_port = int(os.environ.get("STOREFRONT_PORT", "8082"))
        except ValueError as exc:
            raise RuntimeError("PORT, ADMIN_PORT and STOREFRONT_PORT must be integers") from exc
        settings = cls(
            port=port,
            admin_port=admin_port,
            storefront_port=storefront_port,
            webhook_secret=config.env_value("HP_WEBHOOK_SECRET"),
            cron_secret=config.env_value("CRON_SECRET"),
            public_base_url=config.public_base_url_from_environment(),
            job_concurrency=_int_env("HP_JOB_CONCURRENCY", 4, 1),
            schedule=ScheduleSettings.from_env(),
        )
        settings.validate_ports()
        return settings

    @property
    def ports(self) -> dict[str, int]:
        return {"PORT": self.port, "ADMIN_PORT": self.admin_port, "STOREFRONT_PORT": self.storefront_port}

    def validate_ports(self) -> None:
        if any(not 1 <= value <= 65535 for value in self.ports.values()):
            raise RuntimeError("PORT, ADMIN_PORT and STOREFRONT_PORT must be between 1 and 65535")
        if len(set(self.ports.values())) != len(self.ports):
            raise RuntimeError("PORT, ADMIN_PORT and STOREFRONT_PORT must all be different")


def deployment_issues() -> list[str]:
    """Return safe configuration errors for the all-in-one Railway service."""
    issues = config.configuration_issues(webhook=True)
    webhook_secret = config.env_value("HP_WEBHOOK_SECRET")
    cron_secret = config.env_value("CRON_SECRET")
    if webhook_secret and (
        len(webhook_secret) < 24
        or not _TELEGRAM_SECRET_RE.fullmatch(webhook_secret)
    ):
        issues.append(
            "HP_WEBHOOK_SECRET (at least 24 characters using A-Z, a-z, 0-9, _ or -)"
        )
    if cron_secret and len(cron_secret) < 24:
        issues.append("CRON_SECRET (must contain at least 24 characters)")
    if (
        config.env_value("RAILWAY_ENVIRONMENT_ID")
        and not config.env_value("HP_PUBLIC_BASE_URL")
        and not config.env_value("RAILWAY_PUBLIC_DOMAIN")
    ):
        issues.append("Railway public domain (generate one under Networking)")
    return list(dict.fromkeys(issues))
