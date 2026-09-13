"""
Configuration centrale du bot HEAVENPREM.
Toutes les valeurs sensibles sont lues depuis les variables d'environnement.
"""
import os

from dotenv import load_dotenv

load_dotenv()


_SECRET_PLACEHOLDERS = {"[SENSITIVE]", "SENSITIVE"}


def env_value(name: str, default: str = "") -> str:
    """Read a deployment variable while rejecting copied secret placeholders."""
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    if value.upper() in _SECRET_PLACEHOLDERS:
        return ""
    return value


def first_env_value(*names: str, default: str = "") -> str:
    """Return the first usable value among compatible deployment names."""
    for name in names:
        value = env_value(name)
        if value:
            return value
    return default


def normalized_http_url(value: str) -> str:
    """Accept a plain URL and repair Markdown links copied from a chat."""
    value = str(value or "").strip()
    if value.startswith("[") and "](" in value and value.endswith(")"):
        value = value.split("](", 1)[1][:-1].strip()
    return value.rstrip("/")


def mongodb_uri_from_environment() -> str:
    """Return the MongoDB connection string injected by the deployment."""
    return env_value("HP_MONGODB_URI")


def public_base_url_from_environment() -> str:
    """Return the explicit URL or Railway's automatically injected domain."""
    explicit = env_value("HP_PUBLIC_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    railway_domain = env_value("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain:
        if not railway_domain.startswith(("http://", "https://")):
            railway_domain = f"https://{railway_domain}"
        return railway_domain.rstrip("/")
    return "http://127.0.0.1:8080"

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
BOT_TOKEN: str = env_value("HP_BOT_TOKEN")

ADMIN_ID: int = int(os.environ.get("HP_ADMIN_ID", "0"))
CLICK_REPORT_CHAT_ID: int = int(
    os.environ.get("HP_CLICK_REPORT_CHAT_ID", "-1004349965359")
)
SUPPORT_TICKET_CHANNEL_ID: int = int(
    os.environ.get("HP_SUPPORT_TICKET_CHANNEL_ID", "-1004326329551")
)
REQUIRED_CHANNEL: str = os.environ.get("HP_REQUIRED_CHANNEL", "@bmcmethods").strip()
REQUIRED_GROUP: str = os.environ.get("HP_REQUIRED_GROUP", "@Blackmarketgrp").strip()

# ---------------------------------------------------------------------------
# Paiement Binance Pay
# ---------------------------------------------------------------------------
BINANCE_PAY_ID: str = os.environ.get("HP_BINANCE_PAY_ID", "")
USDT_EVM_ADDRESS: str = os.environ.get(
    "HP_USDT_EVM_ADDRESS",
    "0x6529804d712d5ef4bef5c60af4a3683bd7300411",
).strip()
ONCHAIN_BSC_RPC_URL: str = os.environ.get(
    "HP_ONCHAIN_BSC_RPC_URL", "https://bsc-dataseed.bnbchain.org"
).strip()
ONCHAIN_POLYGON_RPC_URL: str = os.environ.get(
    "HP_ONCHAIN_POLYGON_RPC_URL", "https://polygon.drpc.org"
).strip()
USDT_BSC_CONTRACT: str = os.environ.get(
    "HP_USDT_BSC_CONTRACT", "0x55d398326f99059fF775485246999027B3197955"
).strip()
USDT_POLYGON_CONTRACT: str = os.environ.get(
    "HP_USDT_POLYGON_CONTRACT", "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
).strip()
ONCHAIN_VERIFY_TIMEOUT: int = max(
    0, int(os.environ.get("HP_ONCHAIN_VERIFY_TIMEOUT", "45"))
)
ONCHAIN_POLL_INTERVAL: float = max(
    0.5, float(os.environ.get("HP_ONCHAIN_POLL_INTERVAL", "3"))
)

# ---------------------------------------------------------------------------
# Vérification automatique via Binance API (lecture seule)
# ---------------------------------------------------------------------------
BINANCE_API_KEY: str = os.environ.get("HP_BINANCE_API_KEY", "").strip()
BINANCE_API_SECRET: str = os.environ.get("HP_BINANCE_API_SECRET", "").strip()
BINANCE_API_BASE: str = os.environ.get(
    "HP_BINANCE_API_BASE", "https://api.binance.com"
).rstrip("/")

# ---------------------------------------------------------------------------
# Paiement Bybit Pay et vérification automatique (lecture seule)
# ---------------------------------------------------------------------------
BYBIT_UID: str = os.environ.get("HP_BYBIT_UID", "").strip()
BYBIT_API_KEY: str = os.environ.get("HP_BYBIT_API_KEY", "").strip()
BYBIT_API_SECRET: str = os.environ.get("HP_BYBIT_API_SECRET", "").strip()
BYBIT_API_BASE: str = os.environ.get(
    "HP_BYBIT_API_BASE", "https://api.bybit.com"
).rstrip("/")

# ---------------------------------------------------------------------------
# Fournisseur revendeur MailReader
# ---------------------------------------------------------------------------
MAILREADER_API_KEY: str = os.environ.get("HP_MAILREADER_API_KEY", "").strip()
MAILREADER_API_BASE: str = os.environ.get(
    "HP_MAILREADER_API_BASE", "https://api.mailreader.tech"
).rstrip("/")

# ---------------------------------------------------------------------------
# Fournisseur revendeur Shamekh's bot
# ---------------------------------------------------------------------------
SHAMEKH_API_KEY: str = os.environ.get("HP_SHAMEKH_API_KEY", "").strip()
SHAMEKH_API_BASE: str = os.environ.get(
    "HP_SHAMEKH_API_BASE", "https://worker-production-53ca.up.railway.app"
).rstrip("/")

# ---------------------------------------------------------------------------
# Fournisseur revendeur Kakao Shop
# ---------------------------------------------------------------------------
KAKAO_API_KEY: str = os.environ.get("HP_KAKAO_API_KEY", "").strip()
KAKAO_API_BASE: str = os.environ.get(
    "HP_KAKAO_API_BASE", "https://api.shopdigital.app"
).rstrip("/")

# ---------------------------------------------------------------------------
# Fournisseur revendeur VEX Reseller
# ---------------------------------------------------------------------------
VEX_API_KEY: str = os.environ.get("HP_VEX_API_KEY", "").strip()
VEX_API_BASE: str = os.environ.get(
    "HP_VEX_API_BASE",
    "https://api.vexoran.app",
).rstrip("/")

# ---------------------------------------------------------------------------
# Fournisseur revendeur NasTele
# ---------------------------------------------------------------------------
NASTELE_API_KEY: str = first_env_value(
    "HP_NASTELE_API_KEY",
    "NASTELE_API_KEY",
)
NASTELE_API_BASE: str = first_env_value(
    "HP_NASTELE_API_BASE",
    "NASTELE_API_BASE",
    default="https://nastele.online",
).rstrip("/")
NASTELE_VND_PER_USDT: float = float(
    os.environ.get("HP_NASTELE_VND_PER_USDT", "25500")
)

# ---------------------------------------------------------------------------
# Fournisseur revendeur Canboso
# ---------------------------------------------------------------------------
CANBOSO_API_KEY: str = os.environ.get("HP_CANBOSO_API_KEY", "").strip()
CANBOSO_API_BASE: str = os.environ.get(
    "HP_CANBOSO_API_BASE", "https://canboso.com/api/v2/telegram-buyer"
).rstrip("/")
GPT_CHEAP_API_KEY: str = env_value("HP_GPT_CHEAP_API_KEY")
SHOP_CRON_API_KEY: str = env_value("HP_SHOP_CRON_API_KEY")

# ---------------------------------------------------------------------------
# Fournisseur revendeur UPIBot Shop
# ---------------------------------------------------------------------------
UPIBOT_API_KEY: str = env_value("HP_UPIBOT_API_KEY")
UPIBOT_API_BASE: str = os.environ.get(
    "HP_UPIBOT_API_BASE", "https://upibot.00969600.xyz/shop-api/v1"
).rstrip("/")

# ---------------------------------------------------------------------------
# Fonctions IA de l’administration (API externe configurable)
# ---------------------------------------------------------------------------
AI_COMPARISON_API_URL: str = env_value(
    "HP_AI_API_URL", "https://agentrouter.org/v1/chat/completions"
)
AI_COMPARISON_API_URL = normalized_http_url(AI_COMPARISON_API_URL)
AI_COMPARISON_API_KEY: str = env_value("HP_AI_API_KEY")
_AI_COMPARISON_MODELS_RAW: str = env_value(
    "HP_AI_MODELS",
    env_value(
        "HP_AI_MODEL",
        "claude-opus-4-8,claude-opus-5,gpt-5.6-sol",
    ),
)
AI_COMPARISON_MODELS: tuple[str, ...] = tuple(dict.fromkeys(
    model.strip()
    for model in _AI_COMPARISON_MODELS_RAW.split(",")
    if model.strip()
))
AI_COMPARISON_MODEL: str = AI_COMPARISON_MODELS[0] if AI_COMPARISON_MODELS else ""
AI_COMPARISON_AUTH_HEADER: str = env_value(
    "HP_AI_AUTH_HEADER", "Authorization"
)
AI_COMPARISON_AUTH_SCHEME: str = env_value("HP_AI_AUTH_SCHEME", "Bearer")

# ---------------------------------------------------------------------------
# Fournisseur revendeur CGPT Active
# ---------------------------------------------------------------------------
CGPT_ACTIVE_API_KEY: str = first_env_value(
    "HP_CGPT_ACTIVE_API_KEY",
    "CGPT_ACTIVE_API_KEY",
    "HP_CGPT_API_KEY",
    "CGPT_API_KEY",
)
CGPT_ACTIVE_API_BASE: str = first_env_value(
    "HP_CGPT_ACTIVE_API_BASE",
    "CGPT_ACTIVE_API_BASE",
    "HP_CGPT_API_BASE",
    "CGPT_API_BASE",
    default="https://cgpt-active.pro/telegram/api",
).rstrip("/")
_BINANCE_OFFICIAL_BASES = (
    "https://api.binance.com",
    "https://api-gcp.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://api4.binance.com",
)
BINANCE_API_BASES: tuple[str, ...] = tuple(dict.fromkeys(
    [
        BINANCE_API_BASE,
        *[
            value.strip().rstrip("/")
            for value in os.environ.get("HP_BINANCE_API_BASES", "").split(",")
            if value.strip()
        ],
        *_BINANCE_OFFICIAL_BASES,
    ]
))
PAY_CURRENCY: str = os.environ.get("HP_PAY_CURRENCY", "USDT").upper().strip()
TEST_PAYMENT_ENABLED: bool = os.environ.get(
    "HP_TEST_PAYMENT_ENABLED", "false"
).strip().lower() in {"1", "true", "yes", "on"}

# ---------------------------------------------------------------------------
# Vérification via Gmail / Manus (optionnel)
# ---------------------------------------------------------------------------
GMAIL_ACCOUNT: str = os.environ.get("HP_GMAIL_ACCOUNT", "")
MANUS_API_KEY: str = os.environ.get("HP_MANUS_API_KEY", "").strip()
MANUS_API_BASE: str = os.environ.get("HP_MANUS_API_BASE", "https://api.manus.ai")
GMAIL_CONNECTOR_UID: str = os.environ.get("HP_GMAIL_CONNECTOR_UID", "")

# ---------------------------------------------------------------------------
# Base de données
# ---------------------------------------------------------------------------
MONGODB_URI: str = mongodb_uri_from_environment()
MONGODB_DB: str = os.environ.get("HP_MONGODB_DB", "heavenprem").strip()
INVENTORY_KEY: str = env_value("HP_INVENTORY_KEY")
DASHBOARD_PASSWORD: str = env_value("HP_DASHBOARD_PASSWORD")

# ---------------------------------------------------------------------------
# Boutique
# ---------------------------------------------------------------------------
SHOP_NAME: str = os.environ.get("HP_SHOP_NAME", "BlackMarket").strip()
DEFAULT_LANG: str = "en"
SUPPORTED_LANGS: list[str] = ["en"]
CURRENCY: str = "USDT"

# ---------------------------------------------------------------------------
# Affiliation
# ---------------------------------------------------------------------------
AFFILIATE_QUALIFY_CENTS: int = int(os.environ.get("HP_AFFILIATE_QUALIFY_CENTS", "1000"))
AFFILIATE_FIVE_REWARD_CENTS: int = int(os.environ.get("HP_AFFILIATE_FIVE_REWARD_CENTS", "500"))
AFFILIATE_TEN_REWARD_CENTS: int = int(os.environ.get("HP_AFFILIATE_TEN_REWARD_CENTS", "200"))
AFFILIATE_DAILY_CAP: int = int(os.environ.get("HP_AFFILIATE_DAILY_CAP", "10"))
AFFILIATE_MIN_PURCHASE_CENTS: int = int(os.environ.get("HP_AFFILIATE_MIN_PURCHASE_CENTS", "100"))

# ---------------------------------------------------------------------------
# Commandes
# ---------------------------------------------------------------------------
ORDER_EXPIRY_SECONDS: int = int(os.environ.get("HP_ORDER_EXPIRY_SECONDS", "1800"))
PENDING_PAYMENT_TIMEOUT_SECONDS: int = max(
    60, int(os.environ.get("HP_PENDING_PAYMENT_TIMEOUT_SECONDS", "600"))
)
LOW_STOCK_THRESHOLD: int = int(os.environ.get("HP_LOW_STOCK_THRESHOLD", "5"))

# Délai (secondes) max d'attente d'une vérification automatique avant repli manuel.
VERIFY_TIMEOUT: int = int(os.environ.get("HP_VERIFY_TIMEOUT", "120"))
MEMBERSHIP_CACHE_SECONDS: int = max(
    0, int(os.environ.get("HP_MEMBERSHIP_CACHE_SECONDS", "300"))
)


def configuration_issues(*, webhook: bool = False, inventory: bool = False) -> list[str]:
    """Return actionable configuration problems without exposing secret values."""
    required = {
        "HP_BOT_TOKEN": BOT_TOKEN,
        "HP_ADMIN_ID": ADMIN_ID,
        "HP_MONGODB_URI": MONGODB_URI,
    }
    if inventory:
        required["HP_INVENTORY_KEY"] = INVENTORY_KEY
    if webhook:
        required.update({
            "HP_WEBHOOK_SECRET": env_value("HP_WEBHOOK_SECRET"),
            "HP_DASHBOARD_PASSWORD": DASHBOARD_PASSWORD,
            "CRON_SECRET": env_value("CRON_SECRET"),
        })
    issues = [name for name, value in required.items() if not value]
    if MONGODB_URI and not MONGODB_URI.startswith(("mongodb://", "mongodb+srv://")):
        issues.append("HP_MONGODB_URI (invalid MongoDB URI)")
    return issues
