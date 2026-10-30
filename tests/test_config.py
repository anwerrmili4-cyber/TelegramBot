"""Tests for deployment environment parsing."""

import config


def test_mongodb_uri_uses_hp_environment_variable(monkeypatch):
    uri = "mongodb+srv://user:password@example.mongodb.net/app"
    monkeypatch.setenv("HP_MONGODB_URI", uri)

    assert config.mongodb_uri_from_environment() == uri


def test_mongodb_uri_unwraps_quotes_from_raw_variable_import(monkeypatch):
    monkeypatch.setenv("HP_MONGODB_URI", "'mongodb://mongo:27017/app'")

    assert config.mongodb_uri_from_environment() == "mongodb://mongo:27017/app"


def test_mongodb_uri_rejects_vercel_sensitive_placeholder(monkeypatch):
    monkeypatch.setenv("HP_MONGODB_URI", "[SENSITIVE]")

    assert config.mongodb_uri_from_environment() == ""


def test_first_env_value_uses_primary_then_compatible_alias(monkeypatch):
    monkeypatch.delenv("HP_CGPT_ACTIVE_API_KEY", raising=False)
    monkeypatch.setenv("CGPT_ACTIVE_API_KEY", "alias-key")

    assert config.first_env_value(
        "HP_CGPT_ACTIVE_API_KEY", "CGPT_ACTIVE_API_KEY"
    ) == "alias-key"

    monkeypatch.setenv("HP_CGPT_ACTIVE_API_KEY", "preferred-key")
    assert config.first_env_value(
        "HP_CGPT_ACTIVE_API_KEY", "CGPT_ACTIVE_API_KEY"
    ) == "preferred-key"


def test_public_url_uses_railway_generated_domain(monkeypatch):
    monkeypatch.delenv("HP_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "blackmarket.up.railway.app")

    assert (
        config.public_base_url_from_environment()
        == "https://blackmarket.up.railway.app"
    )


def test_explicit_public_url_overrides_railway_domain(monkeypatch):
    monkeypatch.setenv("HP_PUBLIC_BASE_URL", "https://shop.example/")
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "blackmarket.up.railway.app")

    assert config.public_base_url_from_environment() == "https://shop.example"


def test_toolorax_api_base_defaults_to_the_new_domain(monkeypatch):
    monkeypatch.delenv("HP_TOOLORAX_API_BASE", raising=False)

    assert (
        config.toolorax_api_base_from_environment()
        == "https://toolorax.shop/shop-api/v1"
    )


def test_toolorax_api_base_rewrites_the_retired_shopbot_host(monkeypatch):
    monkeypatch.setenv(
        "HP_TOOLORAX_API_BASE",
        "https://shopbot.00969600.xyz/shop-api/v1/",
    )

    assert (
        config.toolorax_api_base_from_environment()
        == "https://toolorax.shop/shop-api/v1"
    )


def test_toolorax_api_base_keeps_a_custom_host(monkeypatch):
    monkeypatch.setenv(
        "HP_TOOLORAX_API_BASE",
        "https://supplier.example/shop-api/v1/",
    )

    assert (
        config.toolorax_api_base_from_environment()
        == "https://supplier.example/shop-api/v1"
    )


def test_configuration_reports_invalid_mongodb_uri(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "token")
    monkeypatch.setattr(config, "ADMIN_ID", 123)
    monkeypatch.setattr(config, "MONGODB_URI", "not-a-mongodb-uri")

    assert config.configuration_issues() == [
        "HP_MONGODB_URI (invalid MongoDB URI)",
    ]
