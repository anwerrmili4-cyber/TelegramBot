from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.domain import binance_dashboard_service as service


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_snapshot_returns_safe_balances_history_and_permissions(monkeypatch):
    monkeypatch.setattr(service, "BINANCE_API_KEY", "public-key")
    monkeypatch.setattr(service, "BINANCE_API_SECRET", "private-secret")
    monkeypatch.setattr(service, "BINANCE_API_BASES", ("https://api.binance.test",))
    monkeypatch.setattr(service.time, "time", lambda: 1_700_000_000)
    requests = []

    def fake_urlopen(request, timeout):
        assert timeout == 15
        assert request.headers["X-mbx-apikey"] == "public-key"
        requests.append(request)
        if request.data:
            signed_query = request.data.decode()
        else:
            signed_query = urlsplit(request.full_url).query
        parsed = parse_qs(signed_query)
        signature = parsed.pop("signature")[0]
        unsigned = signed_query.rsplit("&signature=", 1)[0]
        assert signature == hmac.new(b"private-secret", unsigned.encode(), hashlib.sha256).hexdigest()

        path = urlsplit(request.full_url).path
        payloads = {
            "/sapi/v3/asset/getUserAsset": [
                {"asset": "USDT", "free": "12.5", "locked": "1", "btcValuation": "0.0002"},
                {"asset": "BTC", "free": "0", "locked": "0", "btcValuation": "0"},
            ],
            "/sapi/v1/account/status": {"data": "Normal"},
            "/sapi/v1/account/apiRestrictions": {
                "enableReading": True,
                "enableWithdrawals": False,
                "enableSpotAndMarginTrading": False,
                "enableInternalTransfer": False,
                "ipRestrict": True,
            },
            "/sapi/v1/capital/deposit/hisrec": [{
                "id": "deposit-1", "coin": "USDT", "amount": "5.25", "network": "BSC",
                "status": 1, "address": "0x1234567890abcdef", "txId": "tx1234567890abcdef", "insertTime": 1_699_999_000_000,
            }],
            "/sapi/v1/capital/withdraw/history": [{
                "id": "withdrawal-1", "coin": "BTC", "amount": "0.01", "transactionFee": "0.0001",
                "network": "BTC", "status": 6, "address": "bc1234567890abcdef", "txId": "btc1234567890abcdef",
                "applyTime": "2023-11-14 22:00:00",
            }],
        }
        return _Response(payloads[path])

    monkeypatch.setattr(service, "urlopen", fake_urlopen)
    result = service.snapshot(days=30)

    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["account_status"] == "Normal"
    assert result["permissions"] == {
        "read": True, "withdrawals": False, "trading": False,
        "internal_transfer": False, "ip_restricted": True,
    }
    assert result["balances"] == [{
        "asset": "USDT", "free": 12.5, "locked": 1.0, "total": 13.5, "btc_value": 0.0002,
    }]
    assert result["summary"] == {"assets": 1, "deposits": 1, "withdrawals": 1, "btc_value": 0.0002}
    assert result["transactions"][0]["txid"] == "btc1234567890abcdef"
    assert result["transactions"][0]["address"] == "bc1234…abcdef"
    assert "private-secret" not in json.dumps(result)
    assert requests[0].method == "POST"


def test_snapshot_requires_configured_credentials(monkeypatch):
    monkeypatch.setattr(service, "BINANCE_API_KEY", "")
    monkeypatch.setattr(service, "BINANCE_API_SECRET", "")
    with pytest.raises(service.BinanceDashboardError, match="non configurées"):
        service.snapshot()
