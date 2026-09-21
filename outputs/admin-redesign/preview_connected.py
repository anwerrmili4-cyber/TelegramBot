"""Local UI acceptance preview. Synthetic data only; no bot, database or mutations."""
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2] / "admin-ui" / "dist"
ORDERS = [
    {"id": 1048, "user_id": 101, "username": "demo_camille", "offer_name": "Abonnement créatif", "service_name": "Création", "total_price": 24, "charged_total": 24, "status": "manual_review", "created_at": 1790000000, "product_description": "Accès premium avec outils de création et espace cloud."},
    {"id": 1047, "user_id": 102, "username": "demo_alex", "offer_name": "Outil de productivité", "service_name": "Productivité", "total_price": 18, "charged_total": 18, "status": "delivered", "created_at": 1790000000},
]
CUSTOMERS = [
    {"telegram_id": 101, "username": "demo_camille", "first_name": "Camille", "lang": "fr", "created_at": 1787100000, "last_active_at": 1790000300, "wallet_balance": 46.5, "total_spent": 128, "order_count": 6, "paid_order_count": 5, "referral_count": 3, "ticket_count": 2, "deposit_count": 4, "deposit_total": 180, "last_order_at": 1790000000, "last_order_name": "Abonnement créatif", "banned": False},
    {"telegram_id": 102, "username": "demo_alex", "first_name": "Alex", "lang": "en", "created_at": 1787200000, "last_active_at": 1789900000, "wallet_balance": 8, "total_spent": 64, "order_count": 3, "paid_order_count": 3, "referral_count": 0, "ticket_count": 0, "deposit_count": 2, "deposit_total": 72, "last_order_at": 1790000000, "last_order_name": "Outil de productivité", "banned": False},
    {"telegram_id": 103, "username": "demo_nora", "first_name": "Nora", "lang": "fr", "created_at": 1787300000, "last_active_at": 1788000000, "wallet_balance": 0, "total_spent": 0, "order_count": 0, "paid_order_count": 0, "referral_count": 1, "ticket_count": 1, "deposit_count": 0, "deposit_total": 0, "last_order_at": None, "last_order_name": "", "banned": True},
]
NOTIFICATIONS = [
    {"id": "order:1048:manual_review", "category": "order", "severity": "warning", "title": "Paiement à vérifier", "message": "Commande #1048 · @demo_camille · Abonnement créatif", "created_at": 1790000300, "actionable": True, "target": {"page": "orders", "entity_id": 1048}},
    {"id": "ticket:81:waiting_admin", "category": "support", "severity": "warning", "title": "Réponse client attendue", "message": "Ticket #81 · @demo_camille · Question sur la livraison", "created_at": 1790000200, "actionable": True, "target": {"page": "support", "entity_id": 81}},
    {"id": "offer:7:stock:0", "category": "stock", "severity": "error", "title": "Produit épuisé", "message": "Compte premium annuel · 0 unité disponible", "created_at": 1790000100, "actionable": True, "target": {"page": "inventory", "entity_id": 7}},
    {"id": "topup:31:confirmed", "category": "deposit", "severity": "success", "title": "Dépôt confirmé", "message": "@demo_camille · +50.00 USDT", "created_at": 1789999000, "actionable": False, "target": {"page": "deposits", "entity_id": 31}},
]


def customer_profile(customer):
    customer_orders = [{**row, "qty": 1, "warranty_days": 30} for row in ORDERS if row["user_id"] == customer["telegram_id"]]
    topups = [{"id": 31, "amount": 50, "currency": "USDT", "provider": "binance", "status": "confirmed", "txid": "demo-transaction-31", "created_at": 1789900000}] if customer["telegram_id"] == 101 else []
    tickets = [{"id": 81, "message": "Question sur la livraison de mon produit", "status": "waiting_admin", "created_at": 1789950000, "updated_at": 1790000100}] if customer["telegram_id"] == 101 else []
    warranties = [{"id": 12, "order_id": 1048, "reason": "Accès à vérifier", "status": "pending_admin_check", "refund_amount": 6, "days_used": 2, "created_at": 1790000200}] if customer["telegram_id"] == 101 else []
    timeline = []
    for row in customer_orders:
        timeline.append({"type": "order", "id": row["id"], "title": row["offer_name"], "description": f"Commande #{row['id']}", "status": row["status"], "amount": row["charged_total"], "created_at": row["created_at"]})
    for row in topups:
        timeline.append({"type": "topup", "id": row["id"], "title": "Dépôt portefeuille", "description": "Binance Pay", "status": row["status"], "amount": row["amount"], "created_at": row["created_at"]})
    return {**customer, "orders": customer_orders, "topups": topups, "withdrawals": [], "tickets": tickets, "warranties": warranties, "referrals": [], "affiliate_rewards": [], "affiliate_earned": 6 if customer["telegram_id"] == 101 else 0, "loyalty": {"level": "Gold", "discount_percent": 8, "total_spend": customer["total_spent"]}, "api_purchases": [], "wallet_adjustments": [], "interactions": [{"interaction_type": "button", "action": "catalogue", "created_at": 1790000300}], "interaction_total": 24 if customer["telegram_id"] == 101 else 3, "timeline": sorted(timeline, key=lambda item: item["created_at"], reverse=True), "withdrawal_total": 0}


class Preview(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.reply({"ok": False, "message": "Aperçu de recette : aucune écriture réelle autorisée."}, 403)

    def do_GET(self):
        url = urlsplit(self.path)
        params = parse_qs(url.query)
        path = url.path
        if path == "/admin/api/data":
            self.reply({"shop_name": "Black Market · DÉMO", "preview_mode": True, "currency": "USDT", "bot_username": "demonstration", "summary": {"pending_orders": 1, "open_tickets": 2, "low_stock_offers": 1, "revenue_today": 18, "orders_today": 2, "new_users_today": 1, "available_inventory": 8}, "orders": ORDERS, "services": [], "alerts": [], "users": [], "tickets": []})
        elif path.endswith("-health"):
            self.reply({"ok": False, "message": "Diagnostic non exécuté dans la prévisualisation locale."}, 503)
        elif path == "/admin/api/reseller-providers":
            self.reply({"providers": [{"id": "mailreader", "name": "Fournisseur démo A", "configured": True}, {"id": "shamekh", "name": "Fournisseur démo B", "configured": True}, {"id": "kakao", "name": "Fournisseur démo C", "configured": False}]})
        elif path == "/admin/api/reseller-products":
            self.reply({"supplier_name": "Catalogue de démonstration", "currency": "USDT", "balance": 120, "products": [{"id": "demo-design", "name": "Suite créative", "description": "Exemple de produit pour visualiser le nouveau catalogue. Aucune vente réelle.", "stock": 18, "wholesale_price": 12, "retail_price": 19, "enabled": True, "currency": "USDT"}, {"id": "demo-work", "name": "Espace de productivité", "description": "Une fiche fournisseur avec prix d’achat, prix public et disponibilité.", "stock": 8, "wholesale_price": 9, "retail_price": 15, "enabled": False, "currency": "USDT"}]})
        elif path == "/admin/api/customers" and params.get("user_id"):
            row = next((x for x in CUSTOMERS if str(x["telegram_id"]) == params["user_id"][0]), None)
            self.reply(customer_profile(row) if row else {}, 200 if row else 404)
        elif path == "/admin/api/customers":
            rows = CUSTOMERS
            if params.get("search"):
                rows = [x for x in rows if params["search"][0].lower() in json.dumps(x).lower()]
            self.reply({"items": rows, "page": 1, "pages": 1, "total": len(rows)})
        elif path == "/admin/api/notifications":
            self.reply({"items": NOTIFICATIONS, "generated_at": 1790000300, "poll_after_seconds": 30, "summary": {"total": 4, "critical": 1, "actionable": 3, "information": 1}})
        elif path == "/admin/api/orders" and params.get("detail") == ["1"]:
            row = next((x for x in ORDERS if str(x["id"]) == params.get("order_id", [""])[0]), None)
            self.reply({**row, "customer": {}, "events": [], "inventory": [], "delivery_content": ""} if row else {}, 200 if row else 404)
        elif path.startswith("/admin/api/"):
            rows = ORDERS if path.endswith("orders") else []
            if params.get("status", [""])[0] not in {"", "all"}:
                rows = [x for x in rows if x.get("status") == params["status"][0]]
            if params.get("search"):
                rows = [x for x in rows if params["search"][0].lower() in json.dumps(x).lower()]
            self.reply({"items": rows, "page": 1, "pages": 1, "total": len(rows), "analytics": {"total": 2, "pending": 1, "delivered": 1, "revenue": 18, "statuses": {"manual_review": 1, "delivered": 1}, "daily": [{"date": f"2026-09-{day}", "count": 1 if day == 20 else 0, "revenue": 18 if day == 20 else 0} for day in range(14, 21)]}})
        else:
            relative = path.removeprefix("/admin-v2/") if path.startswith("/admin-v2/assets/") else "index.html"
            file = (ROOT / relative).resolve()
            if not file.is_relative_to(ROOT.resolve()) or not file.is_file():
                self.reply({"error": "not_found"}, 404)
                return
            body = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


if __name__ == "__main__":
    print("Synthetic acceptance preview: http://127.0.0.1:8770/admin/phone", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8770), Preview).serve_forever()
