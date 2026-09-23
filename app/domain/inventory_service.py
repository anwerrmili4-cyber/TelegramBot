"""Service métier pour l'inventaire.

Gère la réservation atomique, la livraison, la libération et le masquage
du contenu sensible.
"""
from __future__ import annotations

import logging
import time

from pymongo import ReturnDocument

import database as db
from app.constants import InventoryStatus, OrderStatus

log = logging.getLogger(__name__)

ACCOUNT_DELIMITER = "###"
MANUAL_STOCK_KEYWORD = "#"


def parse_bulk_inventory(text: str) -> list[str]:
    """Split accounts only on an explicit delimiter line.

    Hashes, URLs, passwords and every other character inside an account are
    preserved verbatim.  The delimiter must be alone on its line.
    """
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for raw_line in (text or "").splitlines():
        if raw_line.strip() == ACCOUNT_DELIMITER:
            if current is not None:
                value = "\n".join(current).strip()
                if not value:
                    raise ValueError(f"Compte sans contenu après {ACCOUNT_DELIMITER}.")
                blocks.append(value)
            current = []
        elif current is None:
            if raw_line.strip():
                raise ValueError(
                    f"Chaque compte doit commencer par {ACCOUNT_DELIMITER}."
                )
        else:
            current.append(raw_line)
    if current is not None:
        value = "\n".join(current).strip()
        if not value:
            raise ValueError(f"Compte sans contenu après {ACCOUNT_DELIMITER}.")
        blocks.append(value)
    if not blocks:
        raise ValueError(
            f"Aucun compte détecté. Commencez chaque compte par {ACCOUNT_DELIMITER}."
        )
    if len(blocks) > 5000:
        raise ValueError("Un import est limité à 5000 comptes.")
    return blocks


def clean_delivery_value(value: str) -> str:
    """Remove only an unambiguous legacy numeric marker.

    A leading ``#`` can be legitimate account content and must be preserved.
    """
    value = str(value or "").strip()
    first_line, separator, remainder = value.partition("\n")
    if separator and first_line.startswith("#") and first_line[1:].strip().isdigit():
        return remainder.strip()
    return value

def sync_offer_stock(offer_id: int) -> int:
    conn = db.get_conn()
    offer = conn.offers.find_one({"id": offer_id}) or {}
    if offer.get("unlimited_stock") or offer.get("manual_stock"):
        return int(offer.get("stock") or 0)
    available = conn.inventory.count_documents({
        "offer_id": offer_id,
        "status": InventoryStatus.AVAILABLE,
    })
    conn.offers.update_one({"id": offer_id}, {"$set": {"stock": available}})
    return available


# ---------------------------------------------------------------------------
# Ajout d'inventaire
# ---------------------------------------------------------------------------

def add_items(offer_id: int, items: list[str]) -> int:
    """Add every non-empty imported account, including identical accounts."""
    conn = db.get_conn()
    # Importing actual credentials restores automatic, inventory-backed stock.
    conn.offers.update_one(
        {"id": offer_id},
        {"$set": {"manual_stock": False, "unlimited_stock": False}},
    )
    cipher = db._fernet()
    added = 0

    for value in (x.strip() for x in items):
        if not value:
            continue
        conn.inventory.insert_one({
            "id": db._next_id("inventory"),
            "offer_id": offer_id,
            "payload": cipher.encrypt(value.encode()).decode(),
            "masked_preview": mask_content(value),
            "status": InventoryStatus.AVAILABLE,
            "reserved_order_id": None,
            "delivered_order_id": None,
            "created_at": int(time.time()),
            "reserved_at": None,
            "delivered_at": None,
        })
        added += 1

    if added:
        sync_offer_stock(offer_id)
        db.audit_event("inventory.added", details={"offer_id": offer_id, "count": added})
        log.info("%d elements added to offer %d", added, offer_id)

    return added

# ---------------------------------------------------------------------------
# Réservation atomique
# ---------------------------------------------------------------------------

def reserve_for_order(offer_id: int, order_id: int, qty: int = 1) -> list[dict] | None:
    """Réserve atomiquement `qty` éléments d'inventaire pour une commande.

    Utilise `findOneAndUpdate` pour chaque élément, garantissant l'atomicité.
    Si le stock est insuffisant, annule toutes les réservations partielles.

    Returns:
        Liste des éléments réservés, ou None si le stock est insuffisant.
    """
    conn = db.get_conn()
    reserved = []

    for _ in range(qty):
        item = conn.inventory.find_one_and_update(
            {"offer_id": offer_id, "status": InventoryStatus.AVAILABLE},
            {
                "$set": {
                    "status": InventoryStatus.RESERVED,
                    "reserved_order_id": order_id,
                    "reserved_at": int(time.time()),
                }
            },
            sort=[("id", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if not item:
            # Stock insuffisant — libérer les réservations partielles
            release_for_order(order_id)
            log.warning("Stock insuffisant pour offre %d, commande #%d", offer_id, order_id)
            return None
        reserved.append(item)

    log.info("%d éléments réservés pour commande #%d", len(reserved), order_id)
    return reserved


def release_for_order(order_id: int) -> int:
    """Libère tout l'inventaire réservé pour une commande."""
    conn = db.get_conn()
    result = conn.inventory.update_many(
        {"reserved_order_id": order_id, "status": InventoryStatus.RESERVED},
        {
            "$set": {"status": InventoryStatus.AVAILABLE, "reserved_order_id": None, "reserved_at": None},
        },
    )
    if result.modified_count:
        log.info("%d éléments libérés pour commande #%d", result.modified_count, order_id)
    return result.modified_count


# ---------------------------------------------------------------------------
# Livraison
# ---------------------------------------------------------------------------

def deliver_for_order(order_id: int) -> list[str] | None:
    """Livre l'inventaire réservé pour une commande payée.

    Déchiffre le contenu, marque les éléments comme livrés et met à jour
    le statut de la commande.

    Returns:
        Liste des valeurs déchiffrées, ou None si la livraison échoue.
    """
    conn = db.get_conn()
    order = conn.orders.find_one({"id": order_id})

    if not order:
        log.error("Commande #%d introuvable pour livraison", order_id)
        return None

    # Empêcher la double livraison
    if order.get("status") == OrderStatus.DELIVERED:
        log.warning("Commande #%d déjà livrée, livraison ignorée", order_id)
        return None

    if order.get("status") not in (OrderStatus.PAID, OrderStatus.PAYMENT_CONFIRMED):
        log.warning("Commande #%d pas en statut payé (%s), livraison impossible", order_id, order.get("status"))
        return None

    # Acquérir atomiquement le droit de livrer. Une deuxième exécution concurrente
    # ne peut plus franchir cette transition.
    claimed = conn.orders.find_one_and_update(
        {
            "id": order_id,
            "status": {"$in": [OrderStatus.PAID, OrderStatus.PAYMENT_CONFIRMED]},
        },
        {
            "$set": {
                "status": OrderStatus.PREPARING_DELIVERY,
                "updated_at": int(time.time()),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        log.warning("Commande #%d déjà prise en charge pour livraison", order_id)
        return None
    order = claimed
    db._capture_admin_notifications()

    # Récupérer les éléments réservés
    reserved_items = list(conn.inventory.find(
        {"reserved_order_id": order_id, "status": InventoryStatus.RESERVED}
    ).sort("id", 1))

    if not reserved_items:
        # Pas d'inventaire réservé — tenter une réservation atomique
        if order.get("offer_id"):
            reserved = reserve_for_order(order["offer_id"], order_id, order.get("qty", 1))
            if not reserved:
                conn.orders.update_one(
                    {"id": order_id, "status": OrderStatus.PREPARING_DELIVERY},
                    {"$set": {"status": OrderStatus.PAYMENT_CONFIRMED, "updated_at": int(time.time())}},
                )
                return None
            reserved_items = reserved
        else:
            conn.orders.update_one(
                {"id": order_id, "status": OrderStatus.PREPARING_DELIVERY},
                {"$set": {"status": OrderStatus.PAYMENT_CONFIRMED, "updated_at": int(time.time())}},
            )
            return None

    # Déchiffrer le contenu
    cipher = db._fernet()
    values = []
    for item in reserved_items:
        try:
            decrypted = cipher.decrypt(item["payload"].encode()).decode()
            values.append(clean_delivery_value(decrypted))
        except Exception as exc:
            log.error("Échec déchiffrement inventaire %s: %s", item.get("_id"), exc)
            conn.orders.update_one(
                {"id": order_id, "status": OrderStatus.PREPARING_DELIVERY},
                {"$set": {"status": OrderStatus.PAYMENT_CONFIRMED, "updated_at": int(time.time())}},
            )
            return None

    # Marquer comme livrés
    now = int(time.time())
    item_ids = [item.get("_id") for item in reserved_items]
    inventory_result = conn.inventory.update_many(
        {
            "_id": {"$in": item_ids},
            "status": InventoryStatus.RESERVED,
            "reserved_order_id": order_id,
        },
        {
            "$set": {
                "status": InventoryStatus.DELIVERED,
                "delivered_order_id": order_id,
                "delivered_at": now,
            }
        },
    )
    if inventory_result.modified_count != len(item_ids):
        log.error("Livraison #%d interrompue: inventaire modifié concurremment", order_id)
        conn.orders.update_one(
            {"id": order_id, "status": OrderStatus.PREPARING_DELIVERY},
            {"$set": {"status": OrderStatus.PAYMENT_CONFIRMED, "updated_at": int(time.time())}},
        )
        return None

    # Mettre à jour la commande
    conn.orders.update_one(
        {"id": order_id, "status": OrderStatus.PREPARING_DELIVERY},
        {
            "$set": {
                "status": OrderStatus.DELIVERED,
                "delivery_text": "[encrypted automatic delivery]",
                "delivered_at": now,
                "updated_at": now,
            }
        },
    )
    if order.get("offer_id"):
        sync_offer_stock(order["offer_id"])

    db.audit_event(
        "order.delivered",
        details={"order_id": order_id, "items_count": len(values)},
    )
    log.info("Commande #%d livrée (%d éléments)", order_id, len(values))
    return values


def set_disabled(item_id: int, disabled: bool = True) -> bool:
    """Disable or re-enable an available inventory item."""
    conn = db.get_conn()
    target = InventoryStatus.DISABLED if disabled else InventoryStatus.AVAILABLE
    source = InventoryStatus.AVAILABLE if disabled else InventoryStatus.DISABLED
    result = conn.inventory.update_one(
        {"id": item_id, "status": source},
        {"$set": {"status": target, "updated_at": int(time.time())}},
    )
    if result.modified_count:
        db.audit_event(
            "inventory.disabled" if disabled else "inventory.enabled",
            details={"inventory_id": item_id},
        )
        return True
    return False


def reveal_item(item_id: int) -> str | None:
    """Decrypt one item after an explicit admin action and audit the access."""
    item = db.get_conn().inventory.find_one({"id": item_id})
    if not item:
        return None
    value = db._fernet().decrypt(item["payload"].encode()).decode()
    db.audit_event("inventory.revealed", details={"inventory_id": item_id, "offer_id": item.get("offer_id")})
    return value


def delivered_content(order_id: int) -> list[str]:
    """Return content already assigned to an order for an explicit admin resend."""
    conn = db.get_conn()
    items = list(conn.inventory.find({
        "delivered_order_id": order_id,
        "status": InventoryStatus.DELIVERED,
    }))
    if not items:
        return []
    cipher = db._fernet()
    values: list[str] = []
    for item in items:
        values.append(clean_delivery_value(cipher.decrypt(item["payload"].encode()).decode()))
    db.audit_event("order.delivery_accessed", details={"order_id": order_id, "items_count": len(values)})
    return values


# ---------------------------------------------------------------------------
# Stats et masquage
# ---------------------------------------------------------------------------

def stats(offer_id: int) -> dict[str, int]:
    """Renvoie les compteurs d'inventaire par statut pour une offre."""
    conn = db.get_conn()
    result: dict[str, int] = {}
    for status in InventoryStatus:
        result[status.value] = conn.inventory.count_documents(
            {"offer_id": offer_id, "status": status.value}
        )
    result["total"] = sum(result.values())
    return result


def mask_content(value: str) -> str:
    """Masque partiellement un contenu sensible pour l'affichage.

    Exemples:
        "user@gmail.com"    → "us***@gmail.com"
        "ABCD-1234-8291"    → "ABCD-****-8291"
        "shortcode"         → "sho***de"
    """
    if not value:
        return "***"

    # Email
    if "@" in value:
        local, domain = value.rsplit("@", 1)
        visible = min(2, len(local))
        return local[:visible] + "***@" + domain

    # Code avec tirets
    if "-" in value:
        parts = value.split("-")
        if len(parts) >= 3:
            masked_parts = [parts[0]] + ["****"] * (len(parts) - 2) + [parts[-1]]
            return "-".join(masked_parts)

    # Générique
    if len(value) <= 4:
        return value[0] + "***"
    visible_start = min(3, len(value) // 3)
    visible_end = min(2, len(value) // 4)
    return value[:visible_start] + "***" + value[-visible_end:] if visible_end else value[:visible_start] + "***"
