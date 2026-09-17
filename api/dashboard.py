"""Rendu HTML/CSS/JS du dashboard administrateur de BlackMarket.

Centralise toute la logique d'affichage du panneau de contrôle avec une
interface moderne, responsive et dynamique (sans rechargement de page).
"""

from __future__ import annotations

import html
import json


def render_dashboard(
    data: dict,
    active_tab: str = "overview",
    dashboard_write_token: str = "",
) -> str:
    """Génère la page HTML complète du dashboard administrateur."""
    allowed_tabs = {"overview", "orders", "catalog", "api-products", "inventory", "customers", "support", "interactions", "activity", "settings"}
    active_tab = active_tab if active_tab in allowed_tabs else "overview"
    summary = data.get("summary", {})
    alerts = data.get("alerts", [])
    currency = data.get("currency", "USDT")
    shop_name = data.get("shop_name", "BlackMarket")

    # Encodage sécurisé en JSON pour JS
    json_data_str = json.dumps(data, default=str)

    # Alertes HTML
    alerts_html = ""
    if alerts:
        for alert in alerts:
            severity_class = f"alert-{alert.get('severity', 'warning')}"
            alerts_html += f"""
            <div class="alert {severity_class}">
                <span class="alert-icon">⚠️</span>
                <span class="alert-message">{html.escape(alert.get('message', ''))}</span>
            </div>
            """
    else:
        alerts_html = '<div class="empty-state"><p>✅ Aucune alerte active. Tout fonctionne normalement.</p></div>'
    # Vue d'ensemble KPI
    conversion_rate = summary.get("conversion_rate", 0.0)
    kpis_html = f"""
    <div class="kpi-grid">
        <div class="kpi-card">
            <h3>Utilisateurs</h3>
            <div class="kpi-value">{summary.get('users', 0)}</div>
            <div class="kpi-subtext">+{summary.get('new_users_today', 0)} aujourd'hui • {summary.get('users_7d_change_pct', 0):+.1f}% vs 7j précédents</div>
        </div>
        <div class="kpi-card">
            <h3>Commandes</h3>
            <div class="kpi-value">{summary.get('orders', 0)}</div>
            <div class="kpi-subtext">{summary.get('paid_orders', 0)} payées • {summary.get('orders_day_delta', 0):+d} vs hier</div>
        </div>
        <div class="kpi-card">
            <h3>Chiffre d'Affaires</h3>
            <div class="kpi-value">{summary.get('revenue_7d', 0.0):.2f} {currency}</div>
            <div class="kpi-subtext">{summary.get('revenue_7d_change_pct', 0):+.1f}% vs 7j précédents • 30j : {summary.get('revenue_30d', 0.0):.2f} {currency}</div>
        </div>
        <div class="kpi-card">
            <h3>Conversion & Stock</h3>
            <div class="kpi-value">{conversion_rate}%</div>
            <div class="kpi-subtext">{summary.get('available_inventory', 0)} codes dispo • {summary.get('open_tickets', 0)} tickets ouverts</div>
        </div>
    </div>
    """

    # Template HTML brut sans formatage de chaine f-string pour éviter les collisions d'accolades avec JS/CSS
    html_template = """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>__SHOP_NAME__ Control Center</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-main: #07101d;
            --bg-card: #111d2e;
            --bg-nav: #0b1728;
            --border-color: #26364d;
            --text-main: #e8eef8;
            --text-muted: #94a3b8;
            --cyan: #67e8f9;
            --cyan-hover: #22d3ee;
            --btn-primary: #0891b2;
            --btn-secondary: #334155;
            --danger: #ef4444;
            --success: #22c55e;
            --warning: #eab308;
            --info: #3b82f6;
            --purple: #a855f7;
            --pink: #ec4899;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-main);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
        }

        /* Navigation latérale desktop */
        aside {
            width: 260px;
            background-color: var(--bg-nav);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            padding: 24px 16px;
            position: sticky;
            top: 0;
            height: 100vh;
            flex: 0 0 260px;
            z-index: 10;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 32px;
            padding: 0 8px;
        }

        .brand h2 {
            color: var(--cyan);
            font-size: 20px;
            font-weight: 700;
            letter-spacing: 0.5px;
        }

        .brand span {
            font-size: 24px;
        }

        nav {
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex-grow: 1;
        }

        nav a {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 12px 16px;
            border-radius: 8px;
            text-align: left;
            font-family: inherit;
            font-size: 15px;
            font-weight: 500;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
            transition: all 0.2s ease;
        }

        nav a:hover {
            background-color: rgba(103, 232, 249, 0.05);
            color: var(--text-main);
        }

        nav a.active {
            background-color: var(--btn-primary);
            color: white;
            box-shadow: 0 4px 12px rgba(8, 145, 178, 0.2);
        }

        /* Zone de contenu principal */
        main {
            flex-grow: 1;
            padding: 40px;
            max-width: 1400px;
            min-width: 0;
            width: 100%;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 32px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 20px;
        }

        header h1 {
            font-size: 28px;
            font-weight: 700;
        }

        .header-actions {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .last-update {
            font-size: 13px;
            color: var(--text-muted);
        }

        .btn {
            padding: 10px 20px;
            border-radius: 8px;
            border: none;
            font-family: inherit;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
            text-decoration: none;
        }

        .btn-primary {
            background-color: var(--btn-primary);
            color: white;
        }

        .btn-primary:hover {
            background-color: var(--cyan-hover);
        }

        .btn-secondary {
            background-color: var(--btn-secondary);
            color: var(--text-main);
            border: 1px solid var(--border-color);
        }

        .btn-secondary:hover {
            background-color: rgba(255, 255, 255, 0.05);
        }

        .btn-danger {
            background-color: var(--danger);
            color: white;
        }

        .btn-danger:hover {
            opacity: 0.9;
        }

        /* Panels */
        .panel {
            display: none;
            animation: fadeIn 0.3s ease-in-out;
        }

        .panel.active {
            display: block;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Grids & Cards */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 20px;
            margin-bottom: 32px;
        }

        .kpi-card {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            position: relative;
            overflow: hidden;
        }

        .kpi-card::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background-color: var(--cyan);
        }

        .kpi-card h3 {
            font-size: 14px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }

        .kpi-value {
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 8px;
            color: var(--text-main);
        }

        .kpi-subtext {
            font-size: 13px;
            color: var(--text-muted);
        }

        /* Alertes */
        .alerts-section {
            margin-bottom: 32px;
        }

        .alert {
            background-color: rgba(234, 179, 8, 0.1);
            border: 1px solid rgba(234, 179, 8, 0.2);
            border-radius: 8px;
            padding: 14px 18px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .alert-error {
            background-color: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }

        .alert-icon {
            font-size: 18px;
        }

        .alert-message {
            font-size: 14px;
            font-weight: 500;
        }

        /* Tables & Wrappers */
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .table-wrap {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 24px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }

        th, td {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
            font-size: 14px;
        }

        th {
            background-color: rgba(255, 255, 255, 0.02);
            font-weight: 600;
            color: var(--text-muted);
            user-select: none;
        }

        tr:last-child td {
            border-bottom: none;
        }

        tr:hover td {
            background-color: rgba(255, 255, 255, 0.01);
        }

        /* Status Badges */
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .badge-pending_payment { background-color: rgba(234, 179, 8, 0.15); color: var(--warning); }
        .badge-awaiting_verification { background-color: rgba(59, 130, 246, 0.15); color: var(--info); }
        .badge-paid, .badge-payment_confirmed { background-color: rgba(34, 197, 94, 0.15); color: var(--success); }
        .badge-delivered { background-color: rgba(168, 85, 247, 0.15); color: var(--purple); }
        .badge-cancelled { background-color: rgba(239, 68, 68, 0.15); color: var(--danger); }
        .badge-expired { background-color: rgba(148, 163, 184, 0.15); color: var(--text-muted); }
        .badge-manual_review { background-color: rgba(249, 115, 22, 0.15); color: #f97316; }
        .badge-refunded { background-color: rgba(236, 72, 153, 0.15); color: var(--pink); }
        .badge-verification_failed { background-color: rgba(239, 68, 68, 0.15); color: var(--danger); }

        /* Forms & Inputs */
        .filters {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 20px;
            align-items: center;
        }

        .search-box {
            flex-grow: 1;
            min-width: 240px;
            position: relative;
        }

        .search-box input {
            width: 100%;
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px 16px;
            color: var(--text-main);
            font-family: inherit;
            font-size: 14px;
        }

        .search-box input:focus {
            outline: none;
            border-color: var(--btn-primary);
        }

        select, input[type="text"], input[type="number"], textarea {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px 14px;
            color: var(--text-main);
            font-family: inherit;
            font-size: 14px;
        }

        select:focus, input:focus, textarea:focus {
            outline: none;
            border-color: var(--btn-primary);
        }

        /* Modals & Dialogs */
        .modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.6);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 100;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.3s ease;
        }

        .modal.active {
            opacity: 1;
            pointer-events: auto;
        }

        .modal-content {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            width: 90%;
            max-width: 500px;
            padding: 28px;
            position: relative;
            transform: scale(0.9);
            transition: transform 0.3s ease;
            max-height: 90vh;
            overflow-y: auto;
        }

        .modal.active .modal-content {
            transform: scale(1);
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .modal-header h3 {
            font-size: 20px;
        }

        .close-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 24px;
            cursor: pointer;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 8px;
            color: var(--text-muted);
        }

        .form-group input, .form-group select, .form-group textarea {
            width: 100%;
        }

        /* Toast Notifications */
        .toast-container {
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 1000;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .toast {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-left: 4px solid var(--cyan);
            border-radius: 8px;
            padding: 16px 20px;
            color: var(--text-main);
            font-size: 14px;
            font-weight: 500;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 300px;
            max-width: 450px;
            animation: slideIn 0.3s ease-out;
        }

        .toast-error {
            border-left-color: var(--danger);
        }

        .notification-center { position:relative; }
        .notification-button { width:42px; height:42px; display:grid; place-items:center; border:1px solid var(--border-color); border-radius:12px; background:rgba(15,29,48,.78); color:var(--text-main); cursor:pointer; position:relative; }
        .notification-button:hover { border-color:var(--cyan); }
        .notification-badge { position:absolute; right:-5px; top:-6px; min-width:19px; height:19px; padding:0 5px; display:none; place-items:center; border-radius:99px; background:var(--danger); color:white; border:2px solid var(--bg-main); font-size:10px; font-weight:800; }
        .notification-badge.visible { display:grid; }
        .notification-panel { position:absolute; right:0; top:50px; width:min(380px,calc(100vw - 30px)); max-height:470px; overflow:hidden; display:none; z-index:90; border:1px solid var(--border-color); border-radius:16px; background:#0d1a2c; box-shadow:0 24px 65px rgba(0,0,0,.45); }
        .notification-panel.open { display:block; }
        .notification-panel-head { padding:16px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid var(--border-color); }
        .notification-panel-head button { border:0; background:transparent; color:var(--cyan); cursor:pointer; font-weight:700; }
        .notification-list { max-height:330px; overflow-y:auto; }
        .notification-item { padding:14px 16px; border-bottom:1px solid var(--border-color); }
        .notification-item strong { display:block; margin-bottom:4px; font-size:13px; }
        .notification-item span { color:var(--text-muted); font-size:12px; }
        .notification-empty { padding:30px 16px; text-align:center; color:var(--text-muted); }
        .notification-permission { width:calc(100% - 24px); margin:12px; justify-content:center; }

        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }

        /* Catalog Layout */
        .catalog-grid {
            display: flex;
            flex-direction: column;
            gap: 24px;
            margin-top: 20px;
        }

        .service-card {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
        }

        .service-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 14px;
            margin-bottom: 20px;
        }

        .service-title {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .service-title h3 {
            font-size: 18px;
            font-weight: 600;
        }

        .offers-list {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .offer-row {
            background-color: rgba(255, 255, 255, 0.01);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 16px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }

        .offer-info {
            flex-grow: 1;
        }

        .offer-name {
            font-weight: 600;
            font-size: 15px;
            margin-bottom: 4px;
        }

        .offer-meta {
            font-size: 13px;
            color: var(--text-muted);
            display: flex;
            gap: 16px;
        }

        .offer-actions {
            display: flex;
            gap: 8px;
        }

        /* External reseller products */
        .supplier-summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 14px;
            margin: 20px 0 24px;
        }

        .supplier-stat {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 18px;
        }

        .supplier-stat span {
            color: var(--text-muted);
            font-size: 13px;
        }

        .supplier-stat strong {
            display: block;
            font-size: 24px;
            margin-top: 7px;
        }

        .api-product-list {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .api-step-nav {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin: 20px 0 24px;
        }

        .api-step-button {
            appearance: none;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 11px;
            color: var(--text-muted);
            cursor: pointer;
            padding: 14px 16px;
            text-align: left;
        }

        .api-step-button strong {
            color: var(--text-main);
            display: block;
            margin-top: 3px;
        }

        .api-step-button.active {
            border-color: #9d72ff;
            background: rgba(157, 114, 255, .13);
            color: #b596ff;
        }

        .api-workspace-page { display: none; }
        .api-workspace-page.active { display: block; }

        .api-action-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 14px;
            margin-top: 20px;
        }

        .api-action-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 18px;
        }

        .api-action-card h3 { margin: 8px 0 6px; }
        .api-action-card p {
            color: var(--text-muted);
            font-size: 13px;
            min-height: 38px;
        }
        .api-action-card .btn { margin-top: 14px; width: 100%; }

        .api-services-strip {
            display: flex;
            align-items: center;
            gap: 9px;
            flex-wrap: wrap;
            margin: 16px 0 20px;
        }

        .api-service-chip {
            background: rgba(255,255,255,.035);
            border: 1px solid var(--border-color);
            border-radius: 999px;
            padding: 8px 12px;
            font-size: 13px;
        }

        .api-product-row {
            align-items: center;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            display: grid;
            gap: 14px;
            grid-template-columns: minmax(220px, 1.5fr) repeat(3, minmax(105px, .55fr)) auto;
            padding: 16px 18px;
        }

        .api-product-row.enabled { border-color: rgba(34, 197, 94, .45); }

        .api-row-stat span {
            color: var(--text-muted);
            display: block;
            font-size: 11px;
            margin-bottom: 4px;
            text-transform: uppercase;
        }

        .api-editor-shell { max-width: 900px; margin: 0 auto; }

        .api-product-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        .api-product-card.published {
            border-color: rgba(245, 158, 11, .55);
        }

        .api-product-card.enabled {
            border-color: rgba(34, 197, 94, .6);
            box-shadow: inset 0 0 0 1px rgba(34, 197, 94, .12);
        }

        .api-product-heading {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
        }

        .api-product-heading h3 {
            font-size: 17px;
            margin-bottom: 4px;
        }

        .api-product-id {
            color: var(--text-muted);
            font-size: 12px;
            word-break: break-all;
        }

        .api-price-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }

        .api-price-box {
            border: 1px solid var(--border-color);
            border-radius: 9px;
            padding: 11px;
            background: rgba(255,255,255,.02);
        }

        .api-price-box span {
            color: var(--text-muted);
            display: block;
            font-size: 12px;
            margin-bottom: 4px;
        }

        .api-profit {
            color: var(--success);
            font-weight: 700;
        }

        .api-profit.loss {
            color: var(--danger);
        }

        .api-product-footer {
            display: flex;
            align-items: flex-end;
            gap: 10px;
            margin-top: auto;
        }

        .api-config-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            padding-top: 4px;
        }

        .api-config-grid .form-group {
            margin: 0;
        }

        .api-config-grid .wide {
            grid-column: 1 / -1;
        }

        .api-config-grid textarea {
            min-height: 82px;
            resize: vertical;
        }

        .api-new-service-fields {
            display: none;
            grid-template-columns: 90px 1fr;
            gap: 10px;
        }

        .api-new-service-fields.visible {
            display: grid;
        }

        .api-product-preview {
            border: 1px solid rgba(245, 158, 11, .28);
            border-radius: 10px;
            background: linear-gradient(135deg, rgba(245, 158, 11, .08), rgba(255,255,255,.02));
            padding: 13px;
        }

        .api-product-preview small {
            color: var(--text-muted);
            display: block;
            margin-bottom: 7px;
            text-transform: uppercase;
            letter-spacing: .08em;
        }

        .api-preview-line {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            font-weight: 650;
        }

        .api-card-actions {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
        }

        .api-statuses {
            display: flex;
            gap: 7px;
            flex-wrap: wrap;
        }

        .api-product-footer .form-group {
            flex: 1;
            margin: 0;
        }

        .api-enabled-control {
            display: inline-flex;
            gap: 8px;
            align-items: center;
            font-weight: 600;
            white-space: nowrap;
        }

        /* Empty state */
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--text-muted);
        }

        /* Responsive */
        @media (max-width: 1024px) {
            body {
                flex-direction: column;
            }
            aside {
                position: sticky;
                top: 0;
                width: 100%;
                height: auto;
                padding: 12px;
                border-right: none;
                border-bottom: 1px solid var(--border-color);
            }
            .brand {
                margin-bottom: 12px;
            }
            nav {
                flex-direction: row;
                overflow-x: auto;
                padding-bottom: 4px;
            }
            nav a {
                white-space: nowrap;
                flex: 0 0 auto;
            }
            main {
                margin-left: 0;
                width: 100%;
                padding: 24px;
            }
            .api-product-row {
                grid-template-columns: 1fr 1fr;
            }
        }

        @media (max-width: 640px) {
            main {
                padding: 16px;
            }
            header {
                align-items: flex-start;
                flex-direction: column;
                gap: 16px;
            }
            .kpi-grid {
                grid-template-columns: 1fr;
            }
            .api-config-grid {
                grid-template-columns: 1fr;
            }
            .api-config-grid .wide {
                grid-column: auto;
            }
            .api-step-nav {
                grid-template-columns: 1fr;
            }
            .api-product-row {
                grid-template-columns: 1fr;
            }
        }

        /* Cryptography / masking values */
        .secret-value {
            font-family: monospace;
            background-color: rgba(255, 255, 255, 0.05);
            padding: 4px 8px;
            border-radius: 4px;
            cursor: pointer;
            user-select: none;
        }

        /* Chat view inside tickets modal */
        .chat-message {
            margin-bottom: 12px;
            padding: 10px 14px;
            border-radius: 8px;
            max-width: 85%;
        }

        .chat-message-client {
            background-color: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.15);
            align-self: flex-start;
            margin-right: auto;
        }

        .chat-message-admin {
            background-color: rgba(8, 145, 178, 0.15);
            border: 1px solid rgba(8, 145, 178, 0.2);
            align-self: flex-end;
            margin-left: auto;
        }

        .chat-time {
            display: block;
            font-size: 10px;
            color: var(--text-muted);
            margin-top: 4px;
            text-align: right;
        }

        .interaction-kpis {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 14px;
            margin: 18px 0 24px;
        }
        .interaction-kpi {
            padding: 18px;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            background: rgba(255,255,255,.025);
        }
        .interaction-kpi strong { display:block; font-size:28px; margin-top:8px; }
        .live-dot {
            display:inline-block; width:9px; height:9px; border-radius:50%;
            background:#22c55e; box-shadow:0 0 12px #22c55e; margin-right:7px;
        }
        .analytics-grid {
            display:grid; grid-template-columns:2fr 1fr; gap:18px; margin-bottom:24px;
        }
        .chart-card {
            border:1px solid var(--border-color); border-radius:12px;
            padding:18px; background:rgba(255,255,255,.02); min-height:250px;
        }
        .daily-chart {
            display:flex; align-items:flex-end; gap:5px; height:180px;
            padding-top:18px; overflow-x:auto;
        }
        .daily-bar-wrap { min-width:18px; flex:1; height:100%; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; }
        .daily-bar { width:100%; min-height:2px; background:linear-gradient(180deg,#22d3ee,#0891b2); border-radius:5px 5px 2px 2px; }
        .daily-label { font-size:9px; color:var(--text-muted); margin-top:6px; transform:rotate(-45deg); white-space:nowrap; }
        .type-row { margin:14px 0; }
        .type-row-head { display:flex; justify-content:space-between; margin-bottom:5px; }
        .type-track { height:9px; background:rgba(255,255,255,.07); border-radius:99px; overflow:hidden; }
        .type-fill { height:100%; background:#22d3ee; border-radius:99px; }
        .interaction-content { max-width:420px; white-space:normal; word-break:break-word; }
        .service-clicks-card { min-height:0; margin-bottom:24px; }
        .service-clicks-head {
            display:flex; align-items:flex-start; justify-content:space-between;
            gap:16px; margin-bottom:16px;
        }
        .service-clicks-head p { margin:5px 0 0; color:var(--text-muted); font-size:13px; }
        .service-clicks-total {
            flex:0 0 auto; padding:7px 11px; border:1px solid var(--border-color);
            border-radius:999px; color:#c4b5fd; background:rgba(157,114,255,.1);
            font-size:12px; font-weight:700;
        }
        .service-click-days {
            display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:12px;
        }
        .service-click-day {
            min-width:0; padding:14px; border:1px solid var(--border-color);
            border-radius:11px; background:rgba(255,255,255,.02);
        }
        .service-click-day-head {
            display:flex; justify-content:space-between; gap:12px; margin-bottom:12px;
            color:var(--text-muted); font-size:12px;
        }
        .service-click-day-head strong { color:var(--text-main); font-size:13px; }
        .service-click-row {
            display:grid; grid-template-columns:minmax(90px,1.1fr) minmax(70px,2fr) auto;
            align-items:center; gap:9px; margin-top:9px; font-size:12px;
        }
        .service-click-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .service-click-track { height:8px; border-radius:99px; overflow:hidden; background:rgba(255,255,255,.07); }
        .service-click-fill { height:100%; border-radius:99px; background:linear-gradient(90deg,#7c3aed,#22d3ee); }
        .service-click-count { min-width:22px; text-align:right; font-weight:800; }
        @media (max-width: 900px) { .analytics-grid { grid-template-columns:1fr; } }
        @media (max-width: 600px) {
            .service-clicks-card { padding:14px; }
            .service-clicks-head { align-items:flex-start; }
            .service-click-days { grid-template-columns:minmax(0,1fr); }
            .service-click-row { grid-template-columns:minmax(82px,1fr) minmax(60px,1.4fr) auto; gap:7px; }
        }

        /* Midnight Merchant visual system */
        :root {
            color-scheme: dark;
            --bg-main: #0b0b0e;
            --bg-card: #111116;
            --bg-nav: #0e0e12;
            --border-color: #2b2b36;
            --text-main: #f5f3f8;
            --text-muted: #92909f;
            --cyan: #9d72ff;
            --cyan-hover: #b596ff;
            --btn-primary: #9d72ff;
            --btn-secondary: #1d1d25;
            --danger: #ff6868;
            --success: #55d992;
            --warning: #ffb547;
            --info: #9d72ff;
            --violet: #9d72ff;
            --purple: #9d72ff;
            --pink: #ff7eb6;
            --panel-raised: #17171e;
            --panel-soft: #1d1d25;
            --line-strong: #3a3948;
            --violet-soft: #241b38;
            --amber-soft: #302313;
            --merchant-shadow: 0 16px 44px rgba(0, 0, 0, .34);
        }

        html {
            background: var(--bg-main);
        }

        body {
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: var(--bg-main);
            letter-spacing: -.01em;
        }

        aside {
            width: 270px;
            flex-basis: 270px;
            padding: 28px 20px 22px;
            background: var(--bg-nav);
            border-color: var(--border-color);
        }

        .brand {
            gap: 12px;
            margin: 0;
            padding: 0 10px 26px;
        }

        .brand-mark {
            width: 42px;
            height: 42px;
            display: grid;
            place-items: center;
            flex: 0 0 auto;
            border-radius: 13px;
            background: var(--violet);
            color: #0d0815;
            font-size: 16px;
            font-weight: 900;
            box-shadow: 0 10px 26px rgba(157, 114, 255, .25);
        }

        .brand-copy strong {
            display: block;
            color: var(--text-main);
            font-size: 17px;
            letter-spacing: -.03em;
        }

        .brand-copy span {
            display: block;
            margin-top: 3px;
            color: var(--text-muted);
            font-size: 10px;
            font-weight: 700;
            letter-spacing: .13em;
            text-transform: uppercase;
        }

        .nav-label {
            margin: 0 11px 9px;
            color: #6e6c79;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: .15em;
            text-transform: uppercase;
        }

        nav {
            gap: 4px;
        }

        nav a {
            min-height: 43px;
            padding: 0 12px;
            border: 1px solid transparent;
            border-radius: 11px;
            color: #aaa8b3;
            font-size: 13px;
            font-weight: 650;
            gap: 12px;
        }

        nav a:hover {
            color: var(--text-main);
            background: #15151b;
            border-color: transparent;
            transform: translateX(2px);
        }

        nav a.active {
            color: #fff;
            background: var(--violet-soft);
            border-color: rgba(157, 114, 255, .34);
            box-shadow: none;
        }

        .nav-icon {
            width: 21px;
            color: currentColor;
            text-align: center;
            font-size: 15px;
        }

        .nav-meta {
            margin-left: auto;
            min-width: 21px;
            height: 21px;
            display: grid;
            place-items: center;
            padding: 0 6px;
            border-radius: 20px;
            color: #16100a;
            background: var(--warning);
            font-size: 10px;
            font-weight: 900;
        }

        .sidebar-bottom {
            margin-top: auto;
            padding: 18px 11px 0;
            border-top: 1px solid var(--border-color);
        }

        .system-line {
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: var(--text-muted);
            font-size: 10px;
        }

        .system-status-dot {
            display: inline-block;
            width: 7px;
            height: 7px;
            margin-right: 6px;
            border-radius: 50%;
            background: var(--success);
            box-shadow: 0 0 0 4px rgba(85, 217, 146, .09);
        }

        .sidebar-version {
            margin-top: 12px;
            color: #5e5c68;
            font-size: 9px;
        }

        main {
            max-width: none;
            padding: 0 34px 38px;
        }

        header.merchant-topbar {
            min-height: 84px;
            display: grid;
            grid-template-columns: minmax(280px, 1fr) auto;
            align-items: center;
            gap: 28px;
            margin: 0;
            padding: 0;
            border-bottom: 1px solid var(--border-color);
        }

        .global-search {
            position: relative;
            width: min(510px, 100%);
        }

        .global-search input {
            width: 100%;
            height: 44px;
            padding: 0 82px 0 42px;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            background: #141419;
            color: var(--text-main);
        }

        .global-search input:focus {
            outline: none;
            border-color: rgba(157, 114, 255, .75);
            box-shadow: 0 0 0 3px rgba(157, 114, 255, .12);
        }

        .search-symbol {
            position: absolute;
            left: 15px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
        }

        .search-shortcut {
            position: absolute;
            right: 10px;
            top: 50%;
            transform: translateY(-50%);
            padding: 5px 7px;
            border: 1px solid var(--border-color);
            border-radius: 7px;
            color: #6f6d78;
            background: #101015;
            font-size: 9px;
            font-weight: 800;
        }

        .merchant-account {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .merchant-account .header-actions {
            gap: 8px;
        }

        .admin-chip {
            display: flex;
            align-items: center;
            gap: 10px;
            min-height: 44px;
            padding: 5px 10px 5px 6px;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            background: var(--bg-card);
        }

        .admin-avatar {
            width: 32px;
            height: 32px;
            display: grid;
            place-items: center;
            border-radius: 9px;
            color: #ded2ff;
            background: var(--violet-soft);
            font-size: 10px;
            font-weight: 900;
        }

        .admin-copy strong,
        .admin-copy span {
            display: block;
        }

        .admin-copy strong {
            font-size: 11px;
        }

        .admin-copy span {
            margin-top: 2px;
            color: var(--text-muted);
            font-size: 9px;
        }

        .merchant-page-head {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            gap: 20px;
            padding: 32px 0 25px;
        }

        .merchant-eyebrow {
            margin-bottom: 8px;
            color: var(--violet);
            font-size: 9px;
            font-weight: 900;
            letter-spacing: .18em;
            text-transform: uppercase;
        }

        .merchant-page-head h1 {
            margin: 0;
            font-size: clamp(28px, 3vw, 42px);
            font-weight: 850;
            letter-spacing: -.055em;
        }

        .merchant-page-head .last-update {
            margin-top: 8px;
        }

        .live-period {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 10px;
            border: 1px solid var(--border-color);
            border-radius: 10px;
            color: var(--text-muted);
            background: var(--bg-card);
            font-size: 10px;
        }

        .live-period::before {
            content: "";
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--success);
            box-shadow: 0 0 0 4px rgba(85, 217, 146, .08);
        }

        .panel {
            animation: merchantPanelIn .18s ease;
        }

        @keyframes merchantPanelIn {
            from { opacity: 0; transform: translateY(4px); }
            to { opacity: 1; transform: none; }
        }

        .kpi-grid {
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin-bottom: 18px;
        }

        .kpi-card {
            position: relative;
            min-height: 142px;
            padding: 20px;
            overflow: hidden;
            border: 1px solid var(--border-color);
            border-radius: 18px;
            background: var(--bg-card);
            box-shadow: none;
        }

        .kpi-card:first-child {
            border-color: rgba(157, 114, 255, .45);
            background: #15121c;
        }

        .kpi-card h3 {
            color: var(--text-muted);
            font-size: 10px;
            font-weight: 750;
            letter-spacing: .02em;
        }

        .kpi-value {
            margin-top: 18px;
            color: var(--text-main);
            font-size: clamp(24px, 2.2vw, 34px);
            font-weight: 850;
            letter-spacing: -.045em;
        }

        .kpi-subtext {
            margin-top: 11px;
            color: var(--success);
            font-size: 10px;
        }

        .merchant-overview-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.8fr) minmax(290px, .8fr);
            gap: 16px;
            align-items: start;
        }

        .merchant-stack {
            display: grid;
            gap: 16px;
        }

        .merchant-card,
        .service-card,
        .chart-card,
        .table-wrap,
        .alerts-section,
        .interaction-kpi {
            border: 1px solid var(--border-color);
            border-radius: 18px;
            background: var(--bg-card);
            box-shadow: none;
        }

        .merchant-card {
            overflow: hidden;
        }

        .merchant-card-head {
            min-height: 62px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 14px;
            padding: 0 18px;
            border-bottom: 1px solid var(--border-color);
        }

        .merchant-card-head h2 {
            font-size: 13px;
            letter-spacing: -.02em;
        }

        .merchant-card-head p {
            margin-top: 3px;
            color: var(--text-muted);
            font-size: 9px;
        }

        .merchant-link {
            border: 0;
            background: transparent;
            color: var(--violet);
            cursor: pointer;
            font-size: 10px;
            font-weight: 700;
        }

        .overview-orders {
            overflow-x: auto;
        }

        .overview-orders table {
            min-width: 700px;
        }

        table {
            background: transparent;
        }

        th {
            color: #777582;
            font-size: 9px;
            font-weight: 850;
            letter-spacing: .08em;
            text-transform: uppercase;
        }

        td {
            border-color: #24242d;
            color: #d4d2da;
            font-size: 11px;
        }

        tbody tr:hover {
            background: #16161d;
        }

        .quick-actions-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            padding: 17px;
        }

        .merchant-action {
            min-height: 96px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            align-items: flex-start;
            padding: 14px;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            background: var(--panel-raised);
            color: var(--text-main);
            cursor: pointer;
            transition: transform .18s ease, border-color .18s ease, background .18s ease;
        }

        .merchant-action:hover {
            transform: translateY(-2px);
            border-color: rgba(157, 114, 255, .5);
            background: #1b1924;
        }

        .merchant-action-icon {
            width: 30px;
            height: 30px;
            display: grid;
            place-items: center;
            border-radius: 9px;
            background: var(--violet-soft);
            color: #c5adff;
            font-weight: 900;
        }

        .merchant-action:nth-child(2) .merchant-action-icon,
        .merchant-action:nth-child(3) .merchant-action-icon {
            color: var(--warning);
            background: var(--amber-soft);
        }

        .merchant-action strong {
            font-size: 11px;
        }

        .merchant-alerts {
            padding: 14px;
        }

        .merchant-alerts .alert {
            min-width: 0;
            margin: 0 0 9px;
            border-radius: 11px;
        }

        .merchant-alerts .empty-state {
            padding: 26px 12px;
        }

        .supplier-overview {
            padding: 18px;
        }

        .supplier-overview-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
        }

        .supplier-identity {
            display: flex;
            align-items: center;
            gap: 11px;
        }

        .supplier-mark {
            width: 38px;
            height: 38px;
            display: grid;
            place-items: center;
            border: 1px solid rgba(157, 114, 255, .3);
            border-radius: 11px;
            color: #c5adff;
            background: var(--violet-soft);
            font-size: 10px;
            font-weight: 950;
        }

        .supplier-identity strong,
        .supplier-identity span {
            display: block;
        }

        .supplier-identity strong {
            font-size: 11px;
        }

        .supplier-identity span {
            margin-top: 4px;
            color: var(--text-muted);
            font-size: 9px;
        }

        .supplier-live {
            color: var(--success);
            font-size: 9px;
            font-weight: 900;
        }

        .supplier-meter {
            height: 6px;
            margin: 17px 0 8px;
            overflow: hidden;
            border-radius: 10px;
            background: #25242d;
        }

        .supplier-meter span {
            display: block;
            width: 0;
            height: 100%;
            background: var(--violet);
            transition: width .3s ease;
        }

        .supplier-copy {
            display: flex;
            justify-content: space-between;
            color: var(--text-muted);
            font-size: 9px;
        }

        .btn {
            min-height: 40px;
            padding: 0 16px;
            border: 1px solid var(--border-color);
            border-radius: 11px;
        }

        .btn-primary {
            border-color: var(--violet);
            background: var(--violet);
            color: #100a19;
        }

        .btn-primary:hover {
            background: var(--cyan-hover);
        }

        .btn-secondary {
            background: var(--panel-soft);
        }

        input,
        textarea,
        select {
            border-color: var(--border-color);
            border-radius: 11px;
            background: #141419;
            color: var(--text-main);
        }

        input:focus,
        textarea:focus,
        select:focus {
            outline: none;
            border-color: rgba(157, 114, 255, .75);
            box-shadow: 0 0 0 3px rgba(157, 114, 255, .12);
        }

        .modal {
            background: rgba(3, 3, 5, .78);
            backdrop-filter: blur(8px);
        }

        .modal-content {
            border: 1px solid var(--line-strong);
            border-radius: 18px;
            background: var(--panel-raised);
            box-shadow: var(--merchant-shadow);
        }

        .toast {
            border-color: rgba(157, 114, 255, .4);
            border-left-color: var(--violet);
            border-radius: 12px;
            background: #191722;
        }

        .api-product-card,
        .supplier-stat {
            border-radius: 18px;
            background: var(--bg-card);
        }

        .api-product-card.enabled {
            border-color: rgba(157, 114, 255, .6);
            box-shadow: inset 0 0 0 1px rgba(157, 114, 255, .12);
        }

        .api-price-box {
            background: var(--panel-raised);
        }

        @media (max-width: 1200px) {
            aside {
                width: 230px;
                flex-basis: 230px;
            }

            main {
                padding-inline: 24px;
            }

            .kpi-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .merchant-overview-grid {
                grid-template-columns: 1fr;
            }

            .merchant-overview-grid > .merchant-stack:last-child {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }

        @media (max-width: 820px) {
            body {
                display: grid;
                grid-template-columns: 76px minmax(0, 1fr);
                align-items: start;
            }

            aside {
                position: sticky;
                width: 76px;
                height: 100vh;
                padding-inline: 10px;
                border-right: 1px solid var(--border-color);
                border-bottom: 0;
            }

            .brand-copy,
            .nav-label,
            nav a .nav-copy,
            .sidebar-bottom {
                display: none;
            }

            .brand {
                justify-content: center;
                padding-inline: 0;
            }

            nav {
                flex-direction: column;
                overflow: visible;
            }

            nav a {
                justify-content: center;
                padding: 0;
            }

            .nav-meta {
                position: absolute;
                margin: 0 0 22px 27px;
            }

            main {
                padding-inline: 20px;
            }

            header.merchant-topbar {
                grid-template-columns: minmax(0, 1fr) auto;
            }

            .admin-copy,
            .header-actions .btn span {
                display: none;
            }

            .merchant-page-head {
                align-items: flex-start;
                flex-direction: column;
            }

            .quick-actions-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }

        @media (max-width: 560px) {
            body {
                display: block;
            }

            aside {
                position: sticky;
                top: 0;
                width: 100%;
                height: auto;
                display: block;
                padding: 10px 12px;
                border-right: 0;
                border-bottom: 1px solid var(--border-color);
            }

            .brand,
            .sidebar-bottom,
            .nav-label {
                display: none;
            }

            nav {
                display: flex;
                flex-direction: row;
                overflow-x: auto;
            }

            nav a {
                min-width: 46px;
                flex: 0 0 46px;
            }

            main {
                padding-inline: 16px;
            }

            header.merchant-topbar {
                min-height: 70px;
                gap: 10px;
            }

            .search-shortcut,
            .admin-chip,
            .header-actions {
                display: none;
            }

            .global-search input {
                padding-right: 14px;
            }

            .kpi-grid,
            .merchant-overview-grid > .merchant-stack:last-child {
                grid-template-columns: 1fr;
            }

            .merchant-page-head {
                padding-top: 24px;
            }

            .quick-actions-grid {
                grid-template-columns: 1fr 1fr;
            }

            .api-product-list {
                grid-template-columns: 1fr;
            }

            .api-product-footer {
                align-items: stretch;
                flex-direction: column;
            }
        }

        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
                animation-duration: .01ms !important;
                animation-iteration-count: 1 !important;
                scroll-behavior: auto !important;
                transition-duration: .01ms !important;
            }
        }

        /* ═══════════════════════════════════════════════════════ */
        /*  PREMIUM VISUAL ENHANCEMENTS                          */
        /* ═══════════════════════════════════════════════════════ */

        /* Animated ambient light orbs */
        body::before {
            content: '';
            position: fixed;
            top: -50%; left: -50%;
            width: 200%; height: 200%;
            background:
                radial-gradient(circle at 20% 50%, rgba(157,114,255,.035) 0%, transparent 50%),
                radial-gradient(circle at 80% 20%, rgba(85,217,146,.025) 0%, transparent 50%),
                radial-gradient(circle at 50% 80%, rgba(255,126,182,.02) 0%, transparent 50%);
            animation: orbFloat 25s ease-in-out infinite;
            pointer-events: none;
            z-index: 0;
        }

        @keyframes orbFloat {
            0%,100% { transform: translate(0,0) rotate(0deg); }
            33%     { transform: translate(2%,-1%) rotate(1deg); }
            66%     { transform: translate(-1%,2%) rotate(-1deg); }
        }

        aside, main { position: relative; z-index: 1; }

        /* ── Glassmorphism KPI cards ── */
        .kpi-card {
            background: rgba(17,17,22,.6) !important;
            backdrop-filter: blur(24px) saturate(1.2);
            -webkit-backdrop-filter: blur(24px) saturate(1.2);
            border: 1px solid rgba(157,114,255,.1) !important;
            transition: transform .28s cubic-bezier(.34,1.56,.64,1),
                        border-color .28s ease, box-shadow .28s ease;
        }

        .kpi-card:hover {
            transform: translateY(-5px);
            border-color: rgba(157,114,255,.35) !important;
            box-shadow: 0 16px 48px rgba(157,114,255,.08),
                        0 0 0 1px rgba(157,114,255,.08);
        }

        .kpi-card::after {
            content: '';
            position: absolute;
            bottom: 0; left: 0; right: 0;
            height: 2px;
            background: linear-gradient(90deg, var(--violet), transparent);
            opacity: 0;
            transition: opacity .3s ease;
        }

        .kpi-card:hover::after { opacity: 1; }
        .kpi-card:nth-child(2)::after { background: linear-gradient(90deg, var(--success), transparent); }
        .kpi-card:nth-child(3)::after { background: linear-gradient(90deg, var(--warning), transparent); }
        .kpi-card:nth-child(4)::after { background: linear-gradient(90deg, var(--pink), transparent); }

        /* ── Glow button effects ── */
        .btn-primary {
            position: relative;
            overflow: hidden;
            transition: all .3s ease, box-shadow .3s ease !important;
        }

        .btn-primary:hover {
            box-shadow: 0 0 22px rgba(157,114,255,.35),
                        0 0 60px rgba(157,114,255,.08) !important;
        }

        .btn-primary::after {
            content: '';
            position: absolute; inset: 0;
            background: linear-gradient(135deg, rgba(255,255,255,.12), transparent 60%);
            opacity: 0;
            transition: opacity .3s ease;
            pointer-events: none;
        }

        .btn-primary:hover::after { opacity: 1; }

        /* Ripple on all buttons */
        .btn { position: relative; overflow: hidden; }

        @keyframes btnRipple {
            to { transform: scale(2.5); opacity: 0; }
        }

        .btn .ripple-circle {
            position: absolute;
            border-radius: 50%;
            background: rgba(255,255,255,.18);
            transform: scale(0);
            animation: btnRipple .55s ease-out;
            pointer-events: none;
        }

        /* ── Skeleton shimmer ── */
        @keyframes skeletonShimmer {
            0%   { background-position: -200px 0; }
            100% { background-position: calc(200px + 100%) 0; }
        }

        .skeleton {
            background: linear-gradient(90deg, #1a1a22 25%, #28283a 50%, #1a1a22 75%);
            background-size: 200px 100%;
            animation: skeletonShimmer 1.4s infinite linear;
            border-radius: 8px;
        }

        .skeleton-kpi {
            min-height: 142px;
            border: 1px solid var(--border-color);
            border-radius: 18px;
            padding: 20px;
        }

        .skeleton-line {
            height: 14px; margin-bottom: 10px; border-radius: 6px;
        }

        .skeleton-line.w60 { width: 60%; }
        .skeleton-line.w40 { width: 40%; }
        .skeleton-line.w80 { width: 80%; }
        .skeleton-line.lg  { height: 30px; width: 45%; margin: 14px 0; }

        /* ── Global progress bar ── */
        .global-progress {
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 3px;
            z-index: 9999;
            pointer-events: none;
            opacity: 0;
            transition: opacity .2s ease;
        }

        .global-progress.active { opacity: 1; }

        .global-progress-bar {
            height: 100%;
            width: 0;
            background: linear-gradient(90deg, var(--violet), #ff7eb6, var(--violet));
            background-size: 200% 100%;
            animation: progressGlow 1.2s ease infinite;
            border-radius: 0 2px 2px 0;
            transition: width .4s ease;
        }

        @keyframes progressGlow {
            0%,100% { background-position: 0% 0; }
            50%     { background-position: 100% 0; }
        }

        /* ── Scroll-to-top button ── */
        .scroll-to-top {
            position: fixed;
            bottom: 28px; right: 80px;
            width: 44px; height: 44px;
            display: grid; place-items: center;
            border: 1px solid var(--border-color);
            border-radius: 13px;
            background: rgba(17,17,22,.88);
            backdrop-filter: blur(14px);
            color: var(--text-main);
            cursor: pointer;
            opacity: 0; transform: translateY(12px);
            transition: opacity .35s ease, transform .35s ease,
                        border-color .25s ease, box-shadow .25s ease;
            z-index: 90;
            font-size: 16px;
        }

        .scroll-to-top.visible {
            opacity: 1; transform: translateY(0);
        }

        .scroll-to-top:hover {
            border-color: var(--violet);
            box-shadow: 0 0 18px rgba(157,114,255,.2);
        }

        /* ── Live pulse ── */
        @keyframes livePulse {
            0%,100% { opacity: 1; box-shadow: 0 0 0 0 rgba(85,217,146,.4); }
            50%     { opacity: .75; box-shadow: 0 0 0 7px rgba(85,217,146,0); }
        }

        .live-dot,
        .system-status-dot,
        .realtime-dot { animation: livePulse 2s ease-in-out infinite; }

        /* ── Sticky table headers ── */
        .table-wrap { max-height: 72vh; overflow-y: auto; }

        .table-wrap thead th {
            position: sticky; top: 0; z-index: 5;
            background: #14141a;
            box-shadow: 0 1px 0 var(--border-color);
        }

        /* ── Row entrance animation ── */
        @keyframes rowSlideIn {
            from { opacity: 0; transform: translateX(-10px); }
            to   { opacity: 1; transform: translateX(0); }
        }

        tbody tr { animation: rowSlideIn .3s ease both; }
        tbody tr:nth-child(1)  { animation-delay: .02s; }
        tbody tr:nth-child(2)  { animation-delay: .04s; }
        tbody tr:nth-child(3)  { animation-delay: .06s; }
        tbody tr:nth-child(4)  { animation-delay: .08s; }
        tbody tr:nth-child(5)  { animation-delay: .1s;  }
        tbody tr:nth-child(6)  { animation-delay: .12s; }
        tbody tr:nth-child(7)  { animation-delay: .14s; }
        tbody tr:nth-child(8)  { animation-delay: .16s; }
        tbody tr:nth-child(9)  { animation-delay: .18s; }
        tbody tr:nth-child(10) { animation-delay: .2s;  }

        tbody tr {
            transition: background .2s ease, transform .15s ease;
        }

        tbody tr:hover {
            background: rgba(157,114,255,.035) !important;
        }

        /* ── Enhanced merchant action cards ── */
        .merchant-action {
            backdrop-filter: blur(8px);
            transition: transform .3s cubic-bezier(.34,1.56,.64,1),
                        border-color .25s ease, box-shadow .25s ease !important;
        }

        .merchant-action:hover {
            transform: translateY(-5px) scale(1.02) !important;
            box-shadow: 0 10px 35px rgba(157,114,255,.1) !important;
        }

        /* ── Card glassmorphism ── */
        .service-card, .merchant-card, .chart-card {
            backdrop-filter: blur(12px);
            transition: border-color .3s ease, box-shadow .3s ease;
        }

        .service-card:hover, .chart-card:hover {
            border-color: rgba(157,114,255,.18);
        }

        /* ── Enhanced modals ── */
        .modal {
            transition: opacity .2s ease !important;
        }

        .modal.active {
            backdrop-filter: blur(14px) !important;
        }

        .modal-content {
            transition: transform .4s cubic-bezier(.34,1.56,.64,1),
                        opacity .25s ease !important;
        }

        .modal.active .modal-content {
            transform: scale(1) translateY(0) !important;
        }

        .modal:not(.active) .modal-content {
            transform: scale(.9) translateY(16px) !important;
        }

        /* ── Enhanced toast ── */
        .toast {
            backdrop-filter: blur(18px);
            animation: toastBounceIn .45s cubic-bezier(.34,1.56,.64,1) !important;
        }

        @keyframes toastBounceIn {
            from { transform: translateX(110%) scale(.85); opacity: 0; }
            to   { transform: translateX(0) scale(1); opacity: 1; }
        }

        /* ── Badge glow ── */
        .badge-paid, .badge-payment_confirmed {
            box-shadow: 0 0 10px rgba(34,197,94,.12);
        }

        .badge-manual_review {
            box-shadow: 0 0 10px rgba(249,115,22,.12);
            animation: livePulse 2.5s ease-in-out infinite;
        }

        /* ── Clock widget ── */
        .topbar-clock {
            display: flex; align-items: center; gap: 8px;
            padding: 6px 14px;
            border: 1px solid var(--border-color);
            border-radius: 10px;
            background: rgba(20,20,25,.75);
            backdrop-filter: blur(8px);
            font-size: 11px; font-weight: 700;
            color: var(--text-muted);
            font-variant-numeric: tabular-nums;
            letter-spacing: .03em;
        }

        .topbar-clock-time {
            color: var(--text-main); font-size: 13px;
        }

        /* ── Offer row accent hover ── */
        .offer-row {
            transition: border-color .25s ease, transform .2s ease,
                        box-shadow .25s ease !important;
        }

        .offer-row:hover {
            border-color: rgba(157,114,255,.22) !important;
            transform: translateX(3px);
            box-shadow: -3px 0 0 var(--violet);
        }

        /* ── Nav active slide indicator ── */
        nav a {
            position: relative;
            transition: all .25s cubic-bezier(.34,1.56,.64,1) !important;
        }

        nav a.active::before {
            content: '';
            position: absolute; left: 0; top: 50%;
            transform: translateY(-50%);
            width: 3px; height: 55%;
            border-radius: 0 4px 4px 0;
            background: var(--violet);
            box-shadow: 0 0 14px rgba(157,114,255,.4);
        }

        /* ── Supplier meter gradient ── */
        .supplier-meter span {
            background: linear-gradient(90deg, var(--violet), #ff7eb6) !important;
            box-shadow: 0 0 14px rgba(157,114,255,.25);
        }

        /* ── Enhanced alert hover ── */
        .alert {
            backdrop-filter: blur(8px);
            transition: transform .2s ease;
        }

        .alert:hover { transform: translateX(4px); }

        /* ── Form focus glow ── */
        input:focus, textarea:focus, select:focus {
            box-shadow: 0 0 0 3px rgba(157,114,255,.14),
                        0 0 22px rgba(157,114,255,.04) !important;
        }

        /* ── KPI counting state ── */
        .kpi-value.counting { color: var(--violet); }

        /* ── Enhanced modal overlay ── */
        .modal.active {
            backdrop-filter: blur(14px);
        }

        /* ── Mobile bottom nav ── */
        @media (max-width: 560px) {
            aside {
                position: fixed !important;
                bottom: 0 !important; top: auto !important;
                left: 0; right: 0;
                width: 100% !important;
                height: auto !important;
                padding: 5px 6px 8px !important;
                border-top: 1px solid var(--border-color);
                border-bottom: 0 !important;
                z-index: 100;
                background: rgba(14,14,18,.93) !important;
                backdrop-filter: blur(22px) saturate(1.3);
                -webkit-backdrop-filter: blur(22px) saturate(1.3);
            }

            nav {
                justify-content: space-around !important;
                gap: 0 !important;
                scrollbar-width: none;
            }

            nav::-webkit-scrollbar { display: none; }

            nav a {
                flex: 1 0 auto !important;
                min-width: 40px !important;
                max-width: 58px;
                flex-direction: column;
                gap: 2px !important;
                padding: 5px 3px !important;
                font-size: 9px !important;
            }

            nav a .nav-icon { font-size: 17px; }
            nav a .nav-copy {
                display: block !important;
                font-size: 7.5px !important;
                text-align: center;
                opacity: .8;
            }

            nav a::before { display: none !important; }

            nav a.active {
                border-radius: 10px;
                background: var(--violet-soft) !important;
            }

            main { padding-bottom: 85px !important; }

            .brand, .sidebar-bottom, .nav-label, .nav-meta {
                display: none !important;
            }

            .scroll-to-top { bottom: 78px; }
            .toast-container { bottom: 80px; }
        }
    </style>
</head>
<body>
    <div class="global-progress" id="global-progress"><div class="global-progress-bar" id="global-progress-bar"></div></div>
    <!-- Barre de navigation latérale -->
    <aside>
        <div class="brand">
            <span class="brand-mark">BM</span>
            <div class="brand-copy">
                <strong>__SHOP_NAME__</strong>
                <span>Commerce Console</span>
            </div>
        </div>
        <div class="nav-label">Workspace</div>
        <nav>
            <a href="/admin" data-tab="overview" data-title="Vue d’ensemble" class="__ACTIVE_OVERVIEW__"><span class="nav-icon">◫</span><span class="nav-copy">Vue d’ensemble</span></a>
            <a href="/admin/orders" data-tab="orders" data-title="Commandes" class="__ACTIVE_ORDERS__"><span class="nav-icon">◎</span><span class="nav-copy">Commandes</span><span class="nav-meta" id="nav-order-count">0</span></a>
            <a href="/admin/catalog" data-tab="catalog" data-title="Catalogue" class="__ACTIVE_CATALOG__"><span class="nav-icon">◆</span><span class="nav-copy">Catalogue</span></a>
            <a href="/admin/api-products" data-tab="api-products" data-title="Produits API" class="__ACTIVE_API-PRODUCTS__"><span class="nav-icon">⌁</span><span class="nav-copy">Produits API</span></a>
            <a href="/admin/inventory" data-tab="inventory" data-title="Inventaire" class="__ACTIVE_INVENTORY__"><span class="nav-icon">▦</span><span class="nav-copy">Inventaire</span></a>
            <a href="/admin/customers" data-tab="customers" data-title="Clients" class="__ACTIVE_CUSTOMERS__"><span class="nav-icon">◉</span><span class="nav-copy">Clients</span></a>
            <a href="/admin/support" data-tab="support" class="__ACTIVE_SUPPORT__" data-title="Support"><span class="nav-icon">◇</span><span class="nav-copy">Support</span><span class="nav-meta" id="nav-support-count">0</span></a>
            <a href="/admin/interactions" data-tab="interactions" data-title="Interactions" class="__ACTIVE_INTERACTIONS__"><span class="nav-icon">⌘</span><span class="nav-copy">Interactions</span></a>
            <a href="/admin/activity" data-tab="activity" data-title="Activité" class="__ACTIVE_ACTIVITY__"><span class="nav-icon">↗</span><span class="nav-copy">Activité</span></a>
            <a href="/admin/settings" data-tab="settings" data-title="Paramètres" class="__ACTIVE_SETTINGS__"><span class="nav-icon">⚙</span><span class="nav-copy">Paramètres</span></a>
            <a href="/admin-v2" data-title="Aperçu React"><span class="nav-icon">⚛</span><span class="nav-copy">Aperçu React</span><span class="nav-meta">Nouveau</span></a>
        </nav>
        <div class="sidebar-bottom">
            <div class="system-line">
                <span><i class="system-status-dot"></i>Systèmes actifs</span>
                <span>Live</span>
            </div>
            <div class="sidebar-version">Admin suite · Midnight Merchant</div>
        </div>
    </aside>

    <!-- Zone principale -->
    <main>
        <header class="merchant-topbar">
            <label class="global-search">
                <span class="search-symbol">⌕</span>
                <input id="global-search" type="search" placeholder="Rechercher commandes, produits ou clients…" aria-label="Recherche globale" onkeydown="runGlobalSearch(event)">
                <span class="search-shortcut">CTRL K</span>
            </label>
            <div class="merchant-account">
                <div class="notification-center">
                    <button class="notification-button" id="notification-button" type="button" onclick="toggleNotificationCenter(event)" aria-label="Centre de notifications" aria-expanded="false">🔔<span class="notification-badge" id="notification-badge">0</span></button>
                    <div class="notification-panel" id="notification-panel">
                        <div class="notification-panel-head"><strong>Notifications</strong><button type="button" onclick="clearAdminNotifications()">Tout effacer</button></div>
                        <div class="notification-list" id="notification-list"></div>
                        <button class="btn btn-secondary notification-permission" id="browser-notification-button" type="button" onclick="enableBrowserNotifications()">Activer les alertes navigateur</button>
                    </div>
                </div>
                <div class="header-actions">
                    <button class="btn btn-secondary" id="telegram-repair-button" onclick="checkAndRepairTelegram()"><span>Réparer Telegram</span></button>
                     <button class="btn btn-secondary" id="binance-test-button" onclick="testBinanceConnection()"><span>Tester Binance</span></button>
                     <button class="btn btn-secondary" id="bybit-test-button" onclick="testBybitConnection()"><span>Tester Bybit</span></button>
                    <button class="btn btn-secondary" onclick="refreshDashboardData()"><span>Actualiser</span></button>
                </div>
                <span class="topbar-clock" id="topbar-clock"><span class="topbar-clock-time" id="clock-time">--:--:--</span></span>
                <div class="admin-chip">
                    <span class="admin-avatar">AD</span>
                    <span class="admin-copy"><strong>Admin</strong><span>Accès propriétaire</span></span>
                </div>
            </div>
        </header>
        <section class="merchant-page-head">
            <div>
                <div class="merchant-eyebrow">Command Center</div>
                <h1 id="panel-title">Vue d’ensemble</h1>
                <p class="last-update">Dernière mise à jour : <span id="last-update-time">-</span></p>
            </div>
            <span class="live-period">Données en direct</span>
        </section>

        <!-- Toast container -->
        <div class="toast-container" id="toast-container"></div>

        <!-- 1. VUE D'ENSEMBLE -->
        <section id="overview" class="panel __PANEL_OVERVIEW__">
            <div id="kpi-container">__KPIS_HTML__</div>
            <div class="merchant-overview-grid">
                <div class="merchant-stack">
                    <article class="merchant-card">
                        <div class="merchant-card-head">
                            <div><h2>Commandes en direct</h2><p>Dernières transactions et livraisons</p></div>
                            <button class="merchant-link" onclick="navigateToTab('orders')">Toutes les commandes →</button>
                        </div>
                        <div class="overview-orders">
                            <table id="overview-orders-table">
                                <thead><tr><th>Commande</th><th>Client</th><th>Produit</th><th>Montant</th><th>Statut</th><th>Date</th></tr></thead>
                                <tbody></tbody>
                            </table>
                        </div>
                    </article>
                    <article class="merchant-card">
                        <div class="merchant-card-head">
                            <div><h2>Actions rapides</h2><p>Contrôles essentiels de la boutique</p></div>
                        </div>
                        <div class="quick-actions-grid">
                            <button class="merchant-action" onclick="openAddOfferModal()"><span class="merchant-action-icon">＋</span><strong>Nouveau produit</strong></button>
                            <button class="merchant-action" onclick="openMaintenanceSettings()"><span class="merchant-action-icon">⚙</span><strong>Maintenance</strong></button>
                            <button class="merchant-action" onclick="openBotBroadcast()"><span class="merchant-action-icon">◁</span><strong>Annonce clients</strong></button>
                            <button class="merchant-action" onclick="syncSupplierCatalog()"><span class="merchant-action-icon">↻</span><strong>Synchroniser API</strong></button>
                        </div>
                    </article>
                </div>
                <div class="merchant-stack">
                    <article class="merchant-card">
                        <div class="merchant-card-head">
                            <div><h2>Alertes système</h2><p>Points nécessitant votre attention</p></div>
                        </div>
                        <div class="merchant-alerts" id="alerts-container">__ALERTS_HTML__</div>
                    </article>
                    <article class="merchant-card">
                        <div class="merchant-card-head">
                            <div><h2>Fournisseur API</h2><p>État de la connexion MailReader</p></div>
                            <button class="merchant-link" onclick="navigateToTab('api-products')">Gérer</button>
                        </div>
                        <div class="supplier-overview" id="overview-supplier">
                            <div class="supplier-overview-row">
                                <div class="supplier-identity">
                                    <span class="supplier-mark">MR</span>
                                    <span><strong>MailReader API</strong><span id="overview-supplier-copy">Vérification de la connexion…</span></span>
                                </div>
                                <span class="supplier-live" id="overview-supplier-status">CONNEXION…</span>
                            </div>
                            <div class="supplier-meter"><span id="overview-supplier-meter"></span></div>
                            <div class="supplier-copy"><span>Solde fournisseur</span><span id="overview-supplier-balance">— USDT</span></div>
                        </div>
                    </article>
                </div>
            </div>
        </section>

        <!-- 2. GESTION DES COMMANDES -->
        <section id="orders" class="panel __PANEL_ORDERS__">
            <div class="filters">
                <div class="search-box">
                    <input type="text" id="order-search" placeholder="Rechercher par ID, client ou produit..." oninput="filterOrders()">
                </div>
                <select id="order-filter-status" onchange="filterOrders()">
                    <option value="">Tous les statuts</option>
                    <option value="pending_payment">En attente de paiement</option>
                    <option value="awaiting_verification">Vérification en cours</option>
                    <option value="payment_confirmed">Paiement confirmé</option>
                    <option value="preparing_delivery">Préparation</option>
                    <option value="delivered">Livrée</option>
                    <option value="verification_failed">Échec vérification</option>
                    <option value="manual_review">Revue manuelle</option>
                    <option value="cancelled">Annulée</option>
                    <option value="refunded">Remboursée</option>
                    <option value="expired">Expirée</option>
                </select>
                <input type="date" id="order-date-from" onchange="filterOrders()" title="Depuis">
                <input type="date" id="order-date-to" onchange="filterOrders()" title="Jusqu'à">
                <select id="order-sort" onchange="filterOrders()">
                    <option value="date">Trier par date</option>
                    <option value="amount">Trier par montant</option>
                </select>
            </div>
            <div class="table-wrap">
                <table id="orders-table">
                    <thead>
                        <tr>
                            <th>Commande</th>
                            <th>Date</th>
                            <th>Client</th>
                            <th>Produit</th>
                            <th>Montant</th>
                            <th>Statut</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Injecté par JS -->
                    </tbody>
                </table>
            </div>
            <div style="display:flex;justify-content:flex-end;align-items:center;gap:12px;margin-top:16px;">
                <button class="btn btn-secondary" id="orders-prev" onclick="changeOrdersPage(-1)">← Précédent</button>
                <span id="orders-page-label">Page 1</span>
                <button class="btn btn-secondary" id="orders-next" onclick="changeOrdersPage(1)">Suivant →</button>
            </div>
        </section>

        <!-- 3. CATALOGUE -->
        <section id="catalog" class="panel __PANEL_CATALOG__">
            <div class="section-header">
                <h2>Services & Offres</h2>
                <div style="display:flex; gap:10px; flex-wrap:wrap;"><button class="btn btn-primary" onclick="openAddOfferModal()">+ Nouveau produit</button><button class="btn btn-secondary" onclick="openModal('add-service-modal')">+ Nouveau service</button></div>
            </div>
            <div class="catalog-grid" id="catalog-list">
                <!-- Injecté par JS -->
            </div>
        </section>

        <!-- PRODUITS FOURNISSEUR API -->
        <section id="api-products" class="panel __PANEL_API-PRODUCTS__">
            <div class="section-header">
                <div>
                    <h2>Centre des API</h2>
                    <p class="last-update">Gérez les fournisseurs, choisissez les produits, puis configurez chaque offre séparément.</p>
                </div>
            </div>

            <div class="api-step-nav">
                <button class="api-step-button active" data-api-step="overview" onclick="showApiWorkspaceStep('overview')">
                    Étape 1<strong>Dashboard des API</strong>
                </button>
                <button class="api-step-button" data-api-step="catalog" onclick="showApiWorkspaceStep('catalog')">
                    Étape 2<strong>Produits & services</strong>
                </button>
                <button class="api-step-button" data-api-step="editor" onclick="showApiWorkspaceStep('editor')">
                    Étape 3<strong>Description, prix & garantie</strong>
                </button>
            </div>

            <div id="api-workspace-overview" class="api-workspace-page active">
                <div id="api-supplier-state">
                    <div class="empty-state">Connexion sécurisée au fournisseur…</div>
                </div>
                <div class="api-action-grid">
                    <div class="api-action-card">
                        <span class="badge badge-paid">API active</span>
                        <h3>MailReader</h3>
                        <p>Fournisseur connecté au catalogue et à la livraison automatique.</p>
                        <button class="btn btn-primary" onclick="selectApiProvider('mailreader')">Voir ses produits</button>
                    </div>
                    <div class="api-action-card">
                        <span class="badge badge-pending">Nouvelle API</span>
                        <h3>Shamekh’s bot</h3>
                        <p>Catalogue, solde et achat automatique via Railway.</p>
                        <button class="btn btn-primary" onclick="selectApiProvider('shamekh')">Voir ses produits</button>
                    </div>
                    <div class="api-action-card">
                        <span class="badge badge-pending">Nouvelle API</span>
                        <h3>Kakao Shop</h3>
                        <p>Produits numériques avec solde et commandes idempotentes.</p>
                        <button class="btn btn-primary" onclick="selectApiProvider('kakao')">Voir ses produits</button>
                    </div>
                    <div class="api-action-card">
                        <span class="badge badge-pending">Nouvelle API</span>
                        <h3>VEX Reseller</h3>
                        <p>Catalogue Supabase avec stock, solde et commandes idempotentes.</p>
                        <button class="btn btn-primary" onclick="selectApiProvider('vex')">Voir ses produits</button>
                    </div>
                    <div class="api-action-card">
                        <span class="badge badge-paid">API active</span>
                        <h3>Piggy AI</h3>
                        <p>Catalogue, solde wallet et achats protégés contre les doublons.</p>
                        <button class="btn btn-primary" onclick="selectApiProvider('canboso')">Voir ses produits</button>
                    </div>
                    <div class="api-action-card">
                        <span class="badge badge-paid">API active</span>
                        <h3>GPT Cheap</h3>
                        <p>Deuxième wallet Canboso indépendant avec sa propre clé et son propre solde.</p>
                        <button class="btn btn-primary" onclick="selectApiProvider('gpt_cheap')">Voir ses produits</button>
                    </div>
                    <div class="api-action-card">
                        <span class="badge badge-paid">API active</span>
                        <h3>Shop Cron</h3>
                        <p>Wallet Canboso indépendant avec catalogue, solde et achats automatiques.</p>
                        <button class="btn btn-primary" onclick="selectApiProvider('shop_cron')">Voir ses produits</button>
                    </div>
                    <div class="api-action-card">
                        <span class="badge badge-paid">API active</span>
                        <h3>UPIBot Shop</h3>
                        <p>Catalogue, solde de dépôt et livraison automatique avec idempotence.</p>
                        <button class="btn btn-primary" onclick="selectApiProvider('upibot')">Voir ses produits</button>
                    </div>
                    <div class="api-action-card">
                        <span class="badge badge-paid">API active</span>
                        <h3>Rich AI Store</h3>
                        <p>Catalogue CDK, solde revendeur et livraison automatique avec idempotence.</p>
                        <button class="btn btn-primary" onclick="selectApiProvider('cgpt_active')">Voir ses produits</button>
                    </div>
                    <div class="api-action-card">
                        <span>↻</span>
                        <h3>Synchronisation</h3>
                        <p>Actualisez le solde, les prix grossistes et les stocks.</p>
                        <button class="btn btn-secondary" id="api-products-refresh" onclick="loadApiProducts(true, activeApiProvider)">Actualiser l’API</button>
                    </div>
                    <div class="api-action-card">
                        <span>＋</span>
                        <h3>Services du bot</h3>
                        <p>Créez une catégorie avant d’y publier des produits.</p>
                        <button class="btn btn-secondary" onclick="openModal('add-service-modal')">Nouveau service</button>
                    </div>
                    <div class="api-action-card">
                        <span>↗</span>
                        <h3>Documentation</h3>
                        <p>Consultez les endpoints et les règles de MailReader.</p>
                        <a class="btn btn-secondary" href="https://api.mailreader.tech/docs" target="_blank" rel="noopener">Ouvrir la documentation</a>
                    </div>
                    <div class="api-action-card" style="grid-column:1/-1;">
                        <span class="badge badge-paid">Votre API revendeur</span>
                        <h3>Clés Buyer API</h3>
                        <p>Créez une clé liée au portefeuille Telegram d’un acheteur. La clé complète ne sera affichée qu’une fois.</p>
                        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:end;">
                            <label style="flex:1;min-width:180px;">Telegram user ID
                                <input id="buyer-api-user-id" type="number" min="1" placeholder="123456789">
                            </label>
                            <label style="flex:1;min-width:180px;">Nom de la clé
                                <input id="buyer-api-label" maxlength="80" value="Reseller API">
                            </label>
                            <button class="btn btn-primary" onclick="createBuyerApiKey()">Créer la clé</button>
                            <a class="btn btn-secondary" href="/api/swagger" target="_blank" rel="noopener">Swagger</a>
                        </div>
                        <div id="buyer-api-created-key" class="alert alert-success" style="display:none;margin-top:12px;word-break:break-all;"></div>
                        <div id="buyer-api-key-list" style="margin-top:12px;"></div>
                    </div>
                </div>
            </div>

            <div id="api-workspace-catalog" class="api-workspace-page">
                <div class="section-header">
                    <div>
                        <h2 id="api-catalog-title">Produits & services MailReader</h2>
                        <p class="last-update">Choisissez un produit pour ouvrir sa configuration complète.</p>
                    </div>
                    <button class="btn btn-secondary" onclick="openModal('add-service-modal')">+ Nouveau service</button>
                </div>
                <div class="api-services-strip" id="api-services-strip"></div>
                <div class="filters">
                    <div class="search-box">
                        <input id="api-product-search" placeholder="Rechercher un produit API…" oninput="filterApiProducts()">
                    </div>
                    <select id="api-product-visibility" onchange="filterApiProducts()">
                        <option value="">Tous les produits</option>
                        <option value="enabled">Publiés</option>
                        <option value="disabled">Brouillons</option>
                        <option value="stock">En stock</option>
                    </select>
                </div>
                <div class="api-product-list" id="api-product-list">
                    <div class="empty-state">Chargement du catalogue…</div>
                </div>
            </div>

            <div id="api-workspace-editor" class="api-workspace-page">
                <div class="api-editor-shell">
                    <button class="btn btn-secondary" style="margin-bottom:16px;" onclick="showApiWorkspaceStep('catalog')">← Retour aux produits</button>
                    <div id="api-product-editor">
                        <div class="empty-state">Choisissez un produit dans l’étape 2 pour modifier sa description, son prix et sa garantie.</div>
                    </div>
                </div>
            </div>
        </section>

        <!-- 4. INVENTAIRE -->
        <section id="inventory" class="panel __PANEL_INVENTORY__">
            <div class="section-header">
                <h2>Codes & Comptes chiffrés</h2>
                <a class="btn btn-secondary" href="/admin/api/inventory-export">⬇ Export CSV masqué</a>
            </div>
            <div class="catalog-grid" id="inventory-list">
                <!-- Injecté par JS -->
            </div>
            <div class="filters" style="margin-top:24px;">
                <div class="search-box"><input id="inventory-search" placeholder="Rechercher une référence masquée..." oninput="filterInventoryItems()"></div>
                <select id="inventory-filter-status" onchange="filterInventoryItems()">
                    <option value="">Tous les statuts</option>
                    <option value="available">Disponible</option>
                    <option value="reserved">Réservé</option>
                    <option value="delivered">Livré</option>
                    <option value="disabled">Désactivé</option>
                </select>
            </div>
            <div class="table-wrap">
                <table id="inventory-table">
                    <thead><tr><th>Référence</th><th>Offre</th><th>Aperçu masqué</th><th>Statut</th><th>Commande</th><th>Actions</th></tr></thead>
                    <tbody></tbody>
                </table>
            </div>
            <div style="display:flex;justify-content:flex-end;align-items:center;gap:12px;margin-top:16px;">
                <button class="btn btn-secondary" id="inventory-prev" onclick="changeInventoryPage(-1)">← Précédent</button>
                <span id="inventory-page-label">Page 1</span>
                <button class="btn btn-secondary" id="inventory-next" onclick="changeInventoryPage(1)">Suivant →</button>
            </div>
        </section>

        <!-- 5. CLIENTS -->
        <section id="customers" class="panel __PANEL_CUSTOMERS__">
            <div class="service-card" style="margin-bottom:20px;">
                <h3 style="margin-bottom:8px;">Créditer le solde de tous les utilisateurs</h3>
                <p class="muted" style="margin-bottom:16px;">
                    Le même montant sera ajouté au portefeuille de chaque utilisateur enregistré.
                    Cette opération ne peut pas être annulée automatiquement.
                </p>
                <form id="bulk-wallet-credit-form" onsubmit="bulkCreditWallets(event)"
                      style="display:grid;grid-template-columns:minmax(180px,1fr) minmax(220px,1fr) auto;gap:12px;align-items:end;">
                    <div class="form-group" style="margin:0;">
                        <label for="bulk-wallet-amount">Montant par utilisateur ($)</label>
                        <input id="bulk-wallet-amount" name="amount" type="number" min="0.01" max="10000"
                               step="0.01" required placeholder="Ex. 5.00">
                    </div>
                    <div class="form-group" style="margin:0;">
                        <label for="bulk-wallet-confirmation">Confirmation</label>
                        <input id="bulk-wallet-confirmation" name="confirmation" required
                               autocomplete="off" placeholder="Saisissez CREDIT ALL">
                    </div>
                    <button id="bulk-wallet-credit-button" class="btn btn-danger" type="submit">
                        Ajouter à tous
                    </button>
                </form>
            </div>
            <div class="filters">
                <div class="search-box">
                    <input type="text" id="customer-search" placeholder="Rechercher par Telegram ID, nom ou prénom..." oninput="filterCustomers()">
                </div>
            </div>
            <div class="table-wrap">
                <table id="customers-table">
                    <thead>
                        <tr>
                            <th>Telegram ID</th>
                            <th>Username</th>
                            <th>Prénom</th>
                            <th>Portefeuille</th>
                            <th>Achats</th>
                            <th>Total dépensé</th>
                            <th>Affiliés</th>
                            <th>Dernière activité</th>
                            <th>Statut</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Injecté par JS -->
                    </tbody>
                </table>
            </div>
        </section>

        <!-- 6. SUPPORT -->
        <section id="support" class="panel __PANEL_SUPPORT__">
            <div class="filters">
                <select id="ticket-filter-status" onchange="filterTickets()">
                    <option value="">Tous les tickets</option>
                    <option value="open">Ouvert</option>
                    <option value="waiting_admin">Attente admin</option>
                    <option value="waiting_customer">Attente client</option>
                    <option value="resolved">Résolu</option>
                    <option value="closed">Fermé</option>
                </select>
            </div>
            <div class="table-wrap">
                <table id="tickets-table">
                    <thead>
                        <tr>
                            <th>Ticket</th>
                            <th>Date</th>
                            <th>Client</th>
                            <th>Catégorie</th>
                            <th>Statut</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Injecté par JS -->
                    </tbody>
                </table>
            </div>
        </section>

        <!-- 7. INTERACTIONS CLIENTS -->
        <section id="interactions" class="panel __PANEL_INTERACTIONS__">
            <div class="section-header">
                <div>
                    <h2>Interactions clients en direct</h2>
                    <p class="last-update">Messages, commandes et clics sur les boutons du bot.</p>
                </div>
                <span><span class="live-dot"></span>Mise à jour automatique</span>
            </div>
            <div class="interaction-kpis" id="interaction-kpis"></div>
            <div class="analytics-grid">
                <div class="chart-card">
                    <h3>Interactions par jour — 30 jours</h3>
                    <div class="daily-chart" id="interactions-daily-chart"></div>
                </div>
                <div class="chart-card">
                    <h3>Répartition des actions</h3>
                    <div id="interactions-type-chart"></div>
                </div>
            </div>
            <div class="chart-card service-clicks-card">
                <div class="service-clicks-head">
                    <div>
                        <h3>Services consultés par jour</h3>
                        <p>Clics des utilisateurs sur chaque service du catalogue pendant les 30 derniers jours.</p>
                    </div>
                    <span class="service-clicks-total" id="service-clicks-summary">0 clic</span>
                </div>
                <div class="service-click-days" id="service-clicks-daily"></div>
            </div>
            <div class="filters">
                <div class="search-box">
                    <input id="interaction-search" placeholder="Nom, username, ID, message ou bouton..." oninput="filterInteractions()">
                </div>
                <select id="interaction-type" onchange="filterInteractions()">
                    <option value="">Toutes les interactions</option>
                    <option value="button">Clic bouton</option>
                    <option value="message">Message</option>
                    <option value="command">Commande</option>
                    <option value="media">Média</option>
                    <option value="other">Autre</option>
                </select>
                <input type="date" id="interaction-date" onchange="filterInteractions()" title="Jour">
            </div>
            <div class="table-wrap">
                <table id="interactions-table">
                    <thead><tr>
                        <th>Date</th><th>Nom</th><th>Username</th><th>Telegram ID</th>
                        <th>Type</th><th>Bouton / commande</th><th>Message / écran</th>
                    </tr></thead>
                    <tbody></tbody>
                </table>
            </div>
        </section>

        <!-- 8. ACTIVITE -->
        <section id="activity" class="panel __PANEL_ACTIVITY__">
            <h2>Journal d'audit système</h2>
            <div class="table-wrap" style="margin-top:20px;">
                <table id="audit-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Action</th>
                            <th>Acteur</th>
                            <th>Détails</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Injecté par JS -->
                    </tbody>
                </table>
            </div>
        </section>

        <!-- 9. CONFIGURATION -->
        <section id="settings" class="panel __PANEL_SETTINGS__">
            <h2>Paramètres de la boutique</h2>
            <div class="table-wrap" style="margin-top:20px; padding:28px;">
                <form id="settings-form" onsubmit="saveSettings(event)">
                    <div class="form-group">
                        <label for="shop-name-input">Nom de la boutique</label>
                        <input type="text" id="shop-name-input" name="shop_name" required>
                    </div>
                    <div class="form-group">
                        <label for="currency-input">Devise de la boutique</label>
                        <input type="text" id="currency-input" name="currency" required>
                    </div>
                    <div class="form-group">
                        <label for="low-stock-input">Seuil global de stock faible</label>
                        <input type="number" id="low-stock-input" name="low_stock_threshold" min="1" required>
                    </div>
                    <div class="form-group">
                        <label for="expiry-input">Délai d'expiration des commandes (secondes)</label>
                        <input type="number" id="expiry-input" name="order_expiry_seconds" min="300" required>
                    </div>
                    <div class="form-group">
                        <label for="payment-recipient-input">Identifiant de paiement</label>
                        <input type="text" id="payment-recipient-input" name="payment_recipient">
                    </div>
                    <div class="form-group">
                        <label><input type="checkbox" id="affiliate-enabled-input" name="affiliate_enabled"> Affiliation active</label>
                    </div>
                    <div class="form-group">
                        <label for="affiliate-target-input">Objectif d'affiliation</label>
                        <input type="number" id="affiliate-target-input" name="affiliate_target" min="1">
                    </div>
                    <div class="form-group">
                        <label for="affiliate-reward-input">Récompense d'affiliation (centimes)</label>
                        <input type="number" id="affiliate-reward-input" name="affiliate_reward_cents" min="0">
                    </div>
                    <div class="form-group">
                        <label><input type="checkbox" id="maintenance-enabled-input" name="maintenance_enabled"> Mode maintenance</label>
                    </div>
                    <div class="form-group">
                        <label for="maintenance-message-input">Message de maintenance</label>
                        <textarea id="maintenance-message-input" name="maintenance_message" maxlength="500"></textarea>
                    </div>
                    <div class="form-group"><label>Message d'accueil personnalisé</label><textarea id="welcome-message-input" name="welcome_message"></textarea></div>
                    <div class="form-group"><label>Message d'aide personnalisé</label><textarea id="help-message-input" name="help_message"></textarea></div>
                    <div class="form-group"><label>Conditions</label><textarea id="terms-message-input" name="terms_message"></textarea></div>
                    <div class="form-group"><label>Confidentialité</label><textarea id="privacy-message-input" name="privacy_message"></textarea></div>
                    <div class="form-group"><label>Langues actives (en,ar)</label><input id="active-languages-input" name="active_languages" value="en,ar"></div>
                    <div class="form-group"><label>Annonce Nouveau Stock (variables : {emoji}, {service}, {offer}, {period}, {warranty}, {price}, {cur}, {stock}, {added})</label><textarea id="announcement-new-stock-input" name="announcement_new_stock" rows="4"></textarea></div>
                    <div class="form-group"><label>Annonce Vente Flash (variables : {emoji}, {service}, {offer}, {period}, {warranty}, {old_price}, {price}, {cur}, {discount}, {remaining})</label><textarea id="announcement-flash-sale-input" name="announcement_flash_sale" rows="4"></textarea></div>
                    <div class="form-group"><label>Annonce Restock / Produit disponible (variables : {emoji}, {service}, {offer}, {period}, {warranty}, {price}, {cur}, {stock})</label><textarea id="announcement-restock-input" name="announcement_restock" rows="4"></textarea></div>
                    <button class="btn btn-primary" type="submit">💾 Enregistrer la configuration</button>
                </form>
            </div>
        </section>
        <button class="scroll-to-top" id="scroll-to-top" aria-label="Retour en haut">↑</button>
    </main>

    <!-- MODALS -->
    <!-- 1. Ajouter Service -->
    <div class="modal" id="add-service-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Ajouter un service</h3>
                <button class="close-btn" onclick="closeModal('add-service-modal')">&times;</button>
            </div>
            <form onsubmit="handleFormSubmit(event, 'add_service')">
                <div class="form-group">
                    <label>Nom du service</label>
                    <input type="text" name="name" required>
                </div>
                <div class="form-group">
                    <label>Emoji</label>
                    <input type="text" name="emoji" placeholder="📦" maxlength="4">
                </div>
                <button class="btn btn-primary" type="submit">Créer</button>
            </form>
        </div>
    </div>

    <!-- 2. Ajouter Offre -->
    <div class="modal" id="add-offer-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Ajouter une offre</h3>
                <button class="close-btn" onclick="closeModal('add-offer-modal')">&times;</button>
            </div>
            <form onsubmit="handleFormSubmit(event, 'add_offer')">
                <div class="form-group"><label>Service</label><select name="service_id" id="add-offer-service-id"></select></div>
                <div class="form-group">
                    <label>Nom de l'offre</label>
                    <input type="text" name="name" required>
                </div>
                <div class="form-group">
                    <label>Prix</label>
                    <input type="number" name="price" step="0.01" min="0" required>
                </div>
                <div class="form-group"><label>Quantité en gros (0 = désactivé)</label><input type="number" name="bulk_quantity" step="1" min="0" value="0"></div>
                <div class="form-group"><label>Prix en gros par unité</label><input type="number" name="bulk_unit_price" step="0.01" min="0"></div>
                <div class="form-group"><label>Période (jours)</label><input type="number" name="period_days" min="1" max="3650" value="30" required></div>
                <div class="form-group"><label>Garantie (jours, 0 = NW)</label><input type="number" name="warranty_days" min="0" max="3650" value="0" required></div>
                <div class="form-group"><label>Description détaillée</label><textarea name="description"></textarea></div>
                <div class="form-group"><label>Comptes initiaux — stock automatique (# = 1 produit)</label><textarea name="initial_inventory" placeholder="#1&#10;Email: compte1@example.com&#10;Password: secret&#10;&#10;#2&#10;Code: produit-2"></textarea></div>
                <div class="form-group"><label>Délai de livraison</label><input name="delivery_delay" value="Instantané après confirmation"></div>
                <div class="form-group"><label>Seuil de stock faible</label><input type="number" name="low_stock_threshold" value="5" min="0"></div>
                <div class="form-group"><label><input type="checkbox" name="auto_delivery" checked> Livraison automatique</label></div>
                <button class="btn btn-primary" type="submit">Créer l'offre</button>
            </form>
        </div>
    </div>

    <div class="modal" id="edit-offer-modal">
        <div class="modal-content">
            <div class="modal-header"><h3>Modifier l'offre</h3><button class="close-btn" onclick="closeModal('edit-offer-modal')">&times;</button></div>
            <form onsubmit="handleFormSubmit(event, 'update_offer')">
                <input type="hidden" name="offer_id" id="edit-offer-id">
                <div class="form-group"><label>Nom</label><input name="name" id="edit-offer-name" required></div>
                <div class="form-group"><label>Description du produit</label><textarea name="description" id="edit-offer-description"></textarea></div>
                <div class="form-group"><label>Période (jours)</label><input type="number" name="period_days" id="edit-offer-period-days" min="1" max="3650" required></div>
                <div class="form-group"><label>Garantie (jours, 0 = NW)</label><input type="number" name="warranty_days" id="edit-offer-warranty-days" min="0" max="3650" required></div>
                <div class="form-group"><label>Prix</label><input type="number" step="0.01" min="0" name="price" id="edit-offer-price" required></div>
                <div class="form-group"><label>Quantité en gros (0 = désactivé)</label><input type="number" step="1" min="0" name="bulk_quantity" id="edit-offer-bulk-quantity"></div>
                <div class="form-group"><label>Prix en gros par unité</label><input type="number" step="0.01" min="0" name="bulk_unit_price" id="edit-offer-bulk-price"></div>
                <div class="form-group"><label>Ordre</label><input type="number" min="0" name="sort_order" id="edit-offer-sort"></div>
                <div class="form-group"><label>Délai de livraison</label><input name="delivery_delay" id="edit-offer-delay"></div>
                <div class="form-group"><label>Seuil de stock faible</label><input type="number" min="0" name="low_stock_threshold" id="edit-offer-threshold"></div>
                <div class="form-group"><label><input type="checkbox" name="auto_delivery" id="edit-offer-auto"> Livraison automatique</label></div>
                <button class="btn btn-primary" type="submit">Enregistrer</button>
            </form>
        </div>
    </div>

    <!-- 3. Ajouter Inventaire -->
    <div class="modal" id="add-inventory-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Ajouter du stock chiffré</h3>
                <button class="close-btn" onclick="closeModal('add-inventory-modal')">&times;</button>
            </div>
            <form onsubmit="handleFormSubmit(event, 'add_inventory')">
                <input type="hidden" name="offer_id" id="add-inventory-offer-id">
                <div class="form-group">
                    <label>Comptes à chiffrer — chaque bloc # compte comme 1 produit</label>
                    <textarea name="items" placeholder="#1&#10;Email: compte1@example.com&#10;Password: secret&#10;&#10;#2&#10;Code: produit-2" required style="min-height: 150px;"></textarea>
                </div>
                <button class="btn btn-primary" type="submit">🔒 Chiffrer & Ajouter</button>
            </form>
        </div>
    </div>

    <!-- 4. Fiche Commande -->
    <div class="modal" id="order-detail-modal">
        <div class="modal-content" style="max-width:600px;">
            <div class="modal-header">
                <h3>Détail de la commande</h3>
                <button class="close-btn" onclick="closeModal('order-detail-modal')">&times;</button>
            </div>
            <div id="order-detail-body">
                <!-- Injecté par JS -->
            </div>
        </div>
    </div>

    <!-- 5. Ticket Conversation -->
    <div class="modal" id="customer-detail-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Fiche client</h3>
                <button class="close-btn" onclick="closeModal('customer-detail-modal')">&times;</button>
            </div>
            <div id="customer-detail-body"></div>
        </div>
    </div>

    <div class="modal" id="ticket-modal">
        <div class="modal-content" style="max-width:700px;">
            <div class="modal-header">
                <h3>Ticket #<span id="ticket-title-id"></span></h3>
                <button class="close-btn" onclick="closeModal('ticket-modal')">&times;</button>
            </div>
            <div id="ticket-chat-area" style="max-height: 350px; overflow-y: auto; margin-bottom: 20px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 8px; display: flex; flex-direction: column;">
                <!-- Injecté par JS -->
            </div>
            <form onsubmit="replyToTicket(event)">
                <input type="hidden" id="ticket-reply-id">
                <div class="form-group">
                    <textarea id="ticket-reply-message" placeholder="Votre réponse au client..." required style="min-height: 80px;"></textarea>
                </div>
                <button class="btn btn-primary" type="submit">✉️ Répondre & Transmettre</button>
            </form>
        </div>
    </div>

    <!-- INJECTION DES DONNEES DANS LE SCRIPT -->
    <script>
        let dashboardData = __JSON_DATA__;
        const dashboardWriteToken = __DASHBOARD_WRITE_TOKEN__;
        let ordersPagination = { page: 1, pages: 1, total: 0 };
        let inventoryPagination = { page: 1, pages: 1, total: 0 };
        let orderFilterTimer;
        let inventoryFilterTimer;
        let resellerCatalog = null;
        let resellerCatalogLoading = false;
        let apiWorkspaceStep = "overview";
        let selectedApiProductId = null;
        let activeApiProvider = dashboardData.reseller?.default_provider || "mailreader";
        let realtimeRequestRunning = false;
        let adminNotifications = loadAdminNotifications();
        let notificationSnapshot = snapshotDashboard(dashboardData);

        // Every dashboard API request must carry the scoped write token. Most
        // browsers preserve Basic Auth for fetch(), but embedded/mobile
        // browsers can omit it on POST requests, which previously caused
        // authenticated offer edits to fail with a misleading 401 response.
        const nativeDashboardFetch = window.fetch.bind(window);
        window.fetch = (input, options = {}) => {
            const requestUrl = new URL(
                typeof input === "string" ? input : input.url,
                window.location.href
            );
            if (
                requestUrl.origin === window.location.origin &&
                requestUrl.pathname.startsWith("/admin")
            ) {
                const headers = new Headers(
                    options.headers || (input instanceof Request ? input.headers : {})
                );
                if (dashboardWriteToken) {
                    headers.set("X-Dashboard-Write-Token", dashboardWriteToken);
                }
                options = {
                    ...options,
                    headers,
                    credentials: "same-origin"
                };
            }
            return nativeDashboardFetch(input, options);
        };

        const ORDER_STATUSES = [
            "pending_payment",
            "awaiting_verification",
            "payment_confirmed",
            "preparing_delivery",
            "delivered",
            "verification_failed",
            "manual_review",
            "cancelled",
            "refunded",
            "expired",
            "paid"
        ];

        // Au chargement de la page
        document.addEventListener("DOMContentLoaded", () => {
            setupTabNavigation();
            refreshUI();
            renderAdminNotifications();
            refreshDashboardData();
            if (document.getElementById("overview")?.classList.contains("active")) {
                loadOverviewSupplier();
            }
            if (document.getElementById("api-products")?.classList.contains("active")) {
                loadApiProducts();
                loadBuyerApiKeys();
            }
        });

        document.addEventListener("click", event => {
            const center = document.querySelector(".notification-center");
            if (center && !center.contains(event.target)) closeNotificationCenter();
        });

        function snapshotDashboard(data) {
            return {
                orders: Number(data?.summary?.orders || 0),
                openTickets: Number(data?.summary?.open_tickets || 0),
                alerts: Array.isArray(data?.alerts) ? data.alerts.length : 0
            };
        }

        function loadAdminNotifications() {
            try { return JSON.parse(localStorage.getItem("admin-notifications-v1") || "[]"); }
            catch (_) { return []; }
        }

        function persistAdminNotifications() {
            localStorage.setItem("admin-notifications-v1", JSON.stringify(adminNotifications.slice(0, 30)));
        }

        function addAdminNotification(title, message, type = "info") {
            const item = { id: Date.now() + Math.random(), title, message, type, createdAt: new Date().toISOString(), unread: true };
            adminNotifications.unshift(item);
            adminNotifications = adminNotifications.slice(0, 30);
            persistAdminNotifications();
            renderAdminNotifications();
            showToast(`${title} · ${message}`, type === "error" ? "error" : "success");
            if ("Notification" in window && Notification.permission === "granted") new Notification(title, { body: message });
        }

        function detectDashboardEvents(previous, current) {
            if (!previous) return;
            const newOrders = current.orders - previous.orders;
            const newTickets = current.openTickets - previous.openTickets;
            if (newOrders > 0) addAdminNotification("Nouvelle commande", `${newOrders} nouvelle${newOrders > 1 ? "s" : ""} commande${newOrders > 1 ? "s" : ""} reçue${newOrders > 1 ? "s" : ""}.`);
            if (newTickets > 0) addAdminNotification("Support", `${newTickets} nouvelle${newTickets > 1 ? "s" : ""} demande${newTickets > 1 ? "s" : ""} à traiter.`);
            if (current.alerts > previous.alerts) addAdminNotification("Alerte système", "Une nouvelle alerte nécessite votre attention.", "error");
        }

        function renderAdminNotifications() {
            const list = document.getElementById("notification-list");
            const badge = document.getElementById("notification-badge");
            if (!list || !badge) return;
            const unread = adminNotifications.filter(item => item.unread).length;
            badge.textContent = unread > 99 ? "99+" : unread;
            badge.classList.toggle("visible", unread > 0);
            list.innerHTML = adminNotifications.length ? adminNotifications.map(item => `<div class="notification-item"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.message)} · ${new Date(item.createdAt).toLocaleString("fr-FR")}</span></div>`).join("") : '<div class="notification-empty">Aucune notification pour le moment.</div>';
            const permissionButton = document.getElementById("browser-notification-button");
            if (permissionButton && "Notification" in window && Notification.permission === "granted") permissionButton.textContent = "Alertes navigateur activées";
        }

        function toggleNotificationCenter(event) {
            event?.stopPropagation();
            const panel = document.getElementById("notification-panel");
            const button = document.getElementById("notification-button");
            const open = !panel.classList.contains("open");
            panel.classList.toggle("open", open);
            button.setAttribute("aria-expanded", String(open));
            if (open) {
                adminNotifications.forEach(item => item.unread = false);
                persistAdminNotifications();
                renderAdminNotifications();
            }
        }

        function closeNotificationCenter() {
            document.getElementById("notification-panel")?.classList.remove("open");
            document.getElementById("notification-button")?.setAttribute("aria-expanded", "false");
        }

        function clearAdminNotifications() {
            adminNotifications = [];
            persistAdminNotifications();
            renderAdminNotifications();
        }

        async function enableBrowserNotifications() {
            if (!("Notification" in window)) return showToast("Ce navigateur ne prend pas en charge les notifications", "error");
            const permission = await Notification.requestPermission();
            renderAdminNotifications();
            showToast(permission === "granted" ? "Alertes navigateur activées" : "Autorisation de notification refusée", permission === "granted" ? "success" : "error");
        }

        function setRealtimeStatus(online) {
            const chip = document.getElementById("realtime-chip");
            const copy = document.getElementById("realtime-copy");
            chip?.classList.toggle("offline", !online);
            if (copy) copy.textContent = online ? "Temps réel actif" : "Connexion interrompue";
        }

        function setupTabNavigation() {
            const buttons = document.querySelectorAll("nav a[data-tab]");
            const panels = document.querySelectorAll(".panel");
            const title = document.getElementById("panel-title");

            function activateTab(btn) {
                const tabId = btn.dataset.tab;
                const panel = document.getElementById(tabId);
                if (!panel) return;

                buttons.forEach(b => b.classList.remove("active"));
                panels.forEach(p => {
                    p.classList.remove("active");
                    p.style.display = "none";
                });
                btn.classList.add("active");
                panel.classList.add("active");
                panel.style.display = "block";
                title.textContent = btn.dataset.title || btn.textContent.trim();
                location.hash = tabId;
                if (tabId === "api-products") {
                    loadApiProducts();
                    loadBuyerApiKeys();
                }
                if (tabId === "overview") loadOverviewSupplier();
                document.querySelector("main").scrollIntoView({ behavior: "smooth", block: "start" });
            }

            buttons.forEach(btn => {
                btn.addEventListener("click", event => {
                    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                    event.preventDefault();
                    history.pushState(null, "", btn.getAttribute("href"));
                    activateTab(btn);
                });
            });

            window.addEventListener("popstate", () => {
                const tabId = location.pathname.replace("/admin/", "") || "overview";
                const button = document.querySelector(`nav a[data-tab="${tabId}"]`);
                if (button) activateTab(button);
            });

            // Gérer le hash initial
            if (location.hash) {
                const tabId = location.hash.substring(1);
                const button = document.querySelector(`nav a[data-tab="${tabId}"]`);
                if (button) activateTab(button);
            } else if (location.pathname.startsWith("/admin/")) {
                const tabId = location.pathname.replace("/admin/", "");
                const button = document.querySelector(`nav a[data-tab="${tabId}"]`);
                if (button) activateTab(button);
            }
        }

        function navigateToTab(tabId) {
            const button = document.querySelector(`nav a[data-tab="${tabId}"]`);
            if (button) button.click();
        }

        function runGlobalSearch(event) {
            if (event.key !== "Enter") return;
            const value = event.currentTarget.value.trim();
            if (!value) return;
            navigateToTab("orders");
            const orderSearch = document.getElementById("order-search");
            orderSearch.value = value;
            filterOrders();
        }

        document.addEventListener("keydown", event => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                document.getElementById("global-search")?.focus();
            }
        });

        function openMaintenanceSettings() {
            navigateToTab("settings");
            setTimeout(() => {
                const control = document.getElementById("maintenance-enabled-input");
                control?.focus();
                control?.scrollIntoView({ behavior: "smooth", block: "center" });
            }, 80);
        }

        function openBotBroadcast() {
            const username = dashboardData.bot_username || "blackmarketa_bot";
            window.open(`https://t.me/${encodeURIComponent(username)}`, "_blank", "noopener");
            showToast("Ouvrez le panneau Admin du bot pour créer l’annonce");
        }

        async function syncSupplierCatalog() {
            navigateToTab("api-products");
            await loadApiProducts(true);
        }

        function showToast(message, type = "success") {
            const container = document.getElementById("toast-container");
            const toast = document.createElement("div");
            toast.className = `toast toast-${type}`;
            toast.innerHTML = `<span>${type === 'success' ? '✅' : '⚠️'}</span> <span>${message}</span>`;
            container.appendChild(toast);
            setTimeout(() => toast.remove(), 4000);
        }

        function openModal(id) {
            document.getElementById(id).classList.add("active");
        }

        function closeModal(id) {
            document.getElementById(id).classList.remove("active");
        }

        function formatDateTime(unixTimestamp) {
            if (!unixTimestamp) return "-";
            const date = new Date(unixTimestamp * 1000);
            return date.toLocaleString('fr-FR');
        }

        function refreshUI() {
            document.getElementById("last-update-time").textContent = new Date().toLocaleTimeString();
            document.getElementById("nav-order-count").textContent = dashboardData.summary?.pending_orders || 0;
            document.getElementById("nav-support-count").textContent = dashboardData.summary?.open_tickets || 0;

            // Vue d'ensemble KPI
            renderAlerts();
            renderKPIs();
            renderOverviewOrders();
            updateOverviewSupplier();

            // Tables & catalogue
            renderOrdersTable();
            renderCatalog();
            renderInventory();
            renderInventoryItems();
            renderCustomersTable();
            renderTicketsTable();
            renderInteractions();
            renderAuditTable();
            fillSettingsForm();
        }

        function renderAlerts() {
            const container = document.getElementById("alerts-container");
            if (!dashboardData.alerts || dashboardData.alerts.length === 0) {
                container.innerHTML = '<div class="empty-state"><p>✅ Aucune alerte active. Tout fonctionne normalement.</p></div>';
                return;
            }
            container.innerHTML = dashboardData.alerts.map(alert => `
                <div class="alert alert-${alert.severity || 'warning'}">
                    <span class="alert-icon">⚠️</span>
                    <span class="alert-message">${alert.message}</span>
                </div>
            `).join("");
        }

        function renderKPIs() {
            const container = document.getElementById("kpi-container");
            const s = dashboardData.summary || {};
            const currency = dashboardData.currency || "USDT";
            const interactions = dashboardData.interactions?.summary || {};
            const apiBalance = resellerCatalog?.balance;
            container.innerHTML = `
                <div class="kpi-grid">
                    <div class="kpi-card">
                        <h3>Chiffre d’affaires · 7 jours</h3>
                        <div class="kpi-value">${Number(s.revenue_7d || 0).toFixed(2)} <small>${currency}</small></div>
                        <div class="kpi-subtext">${Number(s.revenue_7d_change_pct || 0) >= 0 ? "↑" : "↓"} ${Math.abs(Number(s.revenue_7d_change_pct || 0)).toFixed(1)}% par rapport aux 7 jours précédents</div>
                    </div>
                    <div class="kpi-card">
                        <h3>Commandes totales</h3>
                        <div class="kpi-value">${s.orders || 0}</div>
                        <div class="kpi-subtext">${s.paid_orders || 0} payées • ${s.pending_orders || 0} en attente</div>
                    </div>
                    <div class="kpi-card">
                        <h3>Solde fournisseur API</h3>
                        <div class="kpi-value">${apiBalance == null ? "—" : Number(apiBalance).toFixed(2)} <small>USDT</small></div>
                        <div class="kpi-subtext">${dashboardData.reseller?.selected_count || 0} produit(s) sélectionné(s) pour la revente</div>
                    </div>
                    <div class="kpi-card">
                        <h3>Utilisateurs actifs</h3>
                        <div class="kpi-value">${interactions.live_users || 0}</div>
                        <div class="kpi-subtext">${interactions.active_today || 0} actif(s) aujourd’hui • ${s.users || 0} inscrits</div>
                    </div>
                </div>
            `;
        }

        function renderOverviewOrders() {
            const tbody = document.querySelector("#overview-orders-table tbody");
            if (!tbody) return;
            const orders = (dashboardData.orders || []).slice(0, 5);
            if (!orders.length) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Aucune commande récente.</td></tr>';
                return;
            }
            tbody.innerHTML = orders.map(order => `
                <tr>
                    <td><code>#${escapeHtml(order.id)}</code></td>
                    <td><code>${escapeHtml(order.user_id)}</code></td>
                    <td>${escapeHtml(`${order.service_name || ""} — ${order.offer_name || ""}`)}</td>
                    <td>${Number(order.total_price || 0).toFixed(2)} ${escapeHtml(dashboardData.currency || "USDT")}</td>
                    <td><span class="badge badge-${escapeHtml(order.status || "")}">${escapeHtml(order.status || "—")}</span></td>
                    <td>${formatDateTime(order.created_at)}</td>
                </tr>
            `).join("");
        }

        async function loadOverviewSupplier() {
            if (resellerCatalogLoading) return;
            if (resellerCatalog) {
                updateOverviewSupplier();
                return;
            }
            await loadApiProducts();
        }

        function updateOverviewSupplier() {
            const status = document.getElementById("overview-supplier-status");
            const copy = document.getElementById("overview-supplier-copy");
            const balance = document.getElementById("overview-supplier-balance");
            const meter = document.getElementById("overview-supplier-meter");
            if (!status || !copy || !balance || !meter) return;
            if (!resellerCatalog) {
                const configured = Boolean(dashboardData.reseller?.configured);
                status.textContent = configured ? "VÉRIFICATION…" : "À CONFIGURER";
                status.style.color = configured ? "var(--warning)" : "var(--danger)";
                copy.textContent = configured ? "Connexion au fournisseur…" : "Clé API manquante";
                balance.textContent = "— USDT";
                meter.style.width = "0%";
                return;
            }
            const amount = Number(resellerCatalog.balance || 0);
            status.textContent = "● EN LIGNE";
            status.style.color = "var(--success)";
            copy.textContent = `${resellerCatalog.products?.length || 0} produits synchronisés`;
            balance.textContent = `${amount.toFixed(2)} ${resellerCatalog.currency || "USDT"}`;
            meter.style.width = `${Math.max(6, Math.min(100, amount))}%`;
            renderKPIs();
        }

        function renderOrdersTable() {
            const tbody = document.querySelector("#orders-table tbody");
            tbody.innerHTML = "";

            if (!dashboardData.orders || dashboardData.orders.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Aucune commande disponible.</td></tr>';
                return;
            }

            dashboardData.orders.forEach(order => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>#${order.id}</td>
                    <td>${formatDateTime(order.created_at)}</td>
                    <td><code>${order.user_id}</code></td>
                    <td>${order.service_name} — ${order.offer_name}</td>
                    <td>${order.total_price.toFixed(2)} ${dashboardData.currency}</td>
                    <td><span class="badge badge-${order.status}">${order.status}</span></td>
                    <td><button class="btn btn-secondary" style="padding:6px 12px; font-size:12px;" onclick="viewOrderDetail(${order.id})">🔍 Détails</button></td>
                `;
                tbody.appendChild(tr);
            });
        }

        function renderCustomersTable() {
            const tbody = document.querySelector("#customers-table tbody");
            tbody.innerHTML = "";

            if (!dashboardData.users || dashboardData.users.length === 0) {
                tbody.innerHTML = '<tr><td colspan="11" class="empty-state">Aucun membre enregistré.</td></tr>';
                return;
            }

            dashboardData.users.forEach(user => {
                const tr = document.createElement("tr");
                const banLabel = user.banned ? "Débannir" : "Bannir";
                const banClass = user.banned ? "btn-primary" : "btn-danger";
                tr.innerHTML = `
                    <td><code>${user.telegram_id}</code></td>
                    <td>${escapeHtml(user.username ? '@' + user.username : '—')}</td>
                    <td>${escapeHtml(user.first_name || user.full_name || '—')}</td>
                    <td><strong>${Number(user.wallet_balance || 0).toFixed(2)} ${escapeHtml(dashboardData.currency)}</strong></td>
                    <td>${user.paid_order_count || 0} / ${user.order_count || 0}</td>
                    <td>${(user.total_spent || user.total_paid || 0).toFixed(2)} ${dashboardData.currency}</td>
                    <td>${user.referral_count || 0}</td>
                    <td>${user.last_active_at ? formatDateTime(user.last_active_at) : 'Jamais'}</td>
                    <td><span class="badge badge-${user.banned ? 'cancelled' : 'paid'}">${user.banned ? 'Banni' : 'Actif'}</span></td>
                    <td>
                        <button class="btn btn-secondary" style="padding:6px 12px;font-size:12px;" onclick="viewCustomer(${user.telegram_id})">🔍 Profil</button>
                        <button class="btn ${banClass}" style="padding:6px 12px;font-size:12px;" onclick="toggleBanUser(${user.telegram_id}, ${user.banned ? 0 : 1})">${banLabel}</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        function renderCatalog() {
            const list = document.getElementById("catalog-list");
            list.innerHTML = "";

            if (!dashboardData.services || dashboardData.services.length === 0) {
                list.innerHTML = '<div class="empty-state">Aucun service créé.</div>';
                return;
            }

            dashboardData.services.forEach(service => {
                const card = document.createElement("div");
                card.className = "service-card";
                card.innerHTML = `
                    <div class="service-header">
                        <div class="service-title">
                            <span style="font-size:24px;">${service.emoji}</span>
                            <h3>${service.name}</h3>
                        </div>
                        <div style="display:flex; gap:8px;">
                            <button class="btn btn-secondary" onclick="openAddOfferModal(${service.id})">➕ Offre</button>
                            <button class="btn btn-secondary" onclick="toggleService(${service.id}, ${service.active})">${service.active ? '⏸ Désactiver' : '▶️ Activer'}</button>
                        </div>
                    </div>
                    <div class="offers-list" id="offers-for-service-${service.id}"></div>
                `;
                list.appendChild(card);

                const offersListContainer = card.querySelector(`#offers-for-service-${service.id}`);

                if (service.offers && service.offers.length > 0) {
                    service.offers.forEach(offer => {
                        const row = document.createElement("div");
                        row.className = "offer-row";
                        row.innerHTML = `
                            <div class="offer-info">
                                <div class="offer-name">${offer.name}</div>
                                ${offer.description ? `<div style="color:var(--text-muted);font-size:13px;margin-bottom:6px;">${escapeHtml(offer.description)}</div>` : ''}
                                <div class="offer-meta">
                                    <span>💵 Prix : ${offer.price !== null ? offer.price.toFixed(2) : '—'} ${dashboardData.currency}</span>
                                    ${Number(offer.bulk_quantity || 0) > 0 && offer.bulk_unit_price != null ? `<span>📦 Gros : ${Number(offer.bulk_unit_price).toFixed(2)} ${dashboardData.currency} / unité dès ${offer.bulk_quantity}</span>` : ''}
                                    <span>📦 Stock : ${offer.stock}</span>
                                    <span>📝 Note : ${offer.note || '—'}</span>
                                    <span>Livraison : ${offer.delivery_delay || '-'}</span>
                                </div>
                            </div>
                            <div class="offer-actions">
                                <button class="btn btn-secondary" style="padding:6px 12px; font-size:12px;" onclick="openEditOfferModal(${offer.id})">✏️ Éditer</button>
                                <button class="btn btn-secondary" style="padding:6px 12px; font-size:12px;" onclick="duplicateOffer(${offer.id})">📋 Dupliquer</button>
                                <button class="btn btn-secondary" style="padding:6px 12px; font-size:12px;" onclick="toggleOffer(${offer.id}, ${offer.active})">${offer.active ? '⏸' : '▶️'}</button>
                            </div>
                        `;
                        offersListContainer.appendChild(row);
                    });
                } else {
                    offersListContainer.innerHTML = '<div style="color:var(--text-muted); font-size:13px; text-align:center;">Aucune offre pour ce service.</div>';
                }
            });
        }

        async function selectApiProvider(provider) {
            activeApiProvider = provider;
            selectedApiProductId = null;
            resellerCatalog = null;
            await loadApiProducts(true, provider);
            if (resellerCatalog) showApiWorkspaceStep("catalog");
        }

        async function loadBuyerApiKeys() {
            const list = document.getElementById("buyer-api-key-list");
            if (!list) return;
            try {
                const response = await fetch("/admin/api/buyer-keys", {
                    credentials: "same-origin",
                    headers: {"Accept": "application/json"},
                });
                const payload = await response.json();
                if (!response.ok || !payload.ok) throw new Error(payload.error || "Chargement impossible");
                const keys = payload.keys || [];
                list.innerHTML = keys.length ? keys.map(item => `
                    <div class="supplier-summary" style="margin-top:8px;">
                        <div class="supplier-stat"><span>Clé</span><strong>${escapeHtml(item.prefix)}••••</strong></div>
                        <div class="supplier-stat"><span>Utilisateur</span><strong>${item.user_id}</strong></div>
                        <div class="supplier-stat"><span>Nom</span><strong>${escapeHtml(item.label || "Buyer API")}</strong></div>
                        <div class="supplier-stat"><span>État</span><strong>${item.active ? "Active" : "Révoquée"}</strong></div>
                        ${item.active ? `<button class="btn btn-danger" onclick="revokeBuyerApiKey(${item.id})">Révoquer</button>` : ""}
                    </div>`).join("") : '<div class="empty-state">Aucune clé Buyer API.</div>';
            } catch (error) {
                list.innerHTML = `<div class="alert alert-error">${escapeHtml(error.message)}</div>`;
            }
        }

        async function createBuyerApiKey() {
            const userId = Number(document.getElementById("buyer-api-user-id").value);
            const label = document.getElementById("buyer-api-label").value.trim();
            if (!Number.isInteger(userId) || userId <= 0) {
                showToast("Telegram user ID invalide", "error");
                return;
            }
            try {
                const response = await fetch("/admin/api/buyer-keys", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/json",
                        "X-Dashboard-Write-Token": dashboardWriteToken,
                    },
                    body: JSON.stringify({action: "create", user_id: userId, label}),
                });
                const payload = await response.json();
                if (!response.ok || !payload.ok) throw new Error(payload.error || "Création impossible");
                const output = document.getElementById("buyer-api-created-key");
                output.style.display = "block";
                output.innerHTML = `<strong>Copiez cette clé maintenant :</strong><br><code>${escapeHtml(payload.key.key)}</code>`;
                await loadBuyerApiKeys();
                showToast("Clé Buyer API créée");
            } catch (error) {
                showToast(error.message, "error");
            }
        }

        async function revokeBuyerApiKey(keyId) {
            if (!window.confirm("Révoquer immédiatement cette clé API ?")) return;
            try {
                const response = await fetch("/admin/api/buyer-keys", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/json",
                        "X-Dashboard-Write-Token": dashboardWriteToken,
                    },
                    body: JSON.stringify({action: "revoke", key_id: keyId}),
                });
                const payload = await response.json();
                if (!response.ok || !payload.ok) throw new Error(payload.error || "Révocation impossible");
                await loadBuyerApiKeys();
                showToast("Clé révoquée");
            } catch (error) {
                showToast(error.message, "error");
            }
        }

        async function loadApiProducts(force = false, provider = activeApiProvider) {
            if (provider !== activeApiProvider) {
                activeApiProvider = provider;
                resellerCatalog = null;
                selectedApiProductId = null;
            }
            if (resellerCatalogLoading || (resellerCatalog && !force)) {
                if (resellerCatalog) renderApiProducts();
                return;
            }
            resellerCatalogLoading = true;
            const refreshButton = document.getElementById("api-products-refresh");
            if (refreshButton) refreshButton.disabled = true;
            try {
                const response = await fetch(`/admin/api/reseller-products?provider=${encodeURIComponent(activeApiProvider)}`, {
                    headers: { "Accept": "application/json" }
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Connexion fournisseur impossible.");
                }
                resellerCatalog = result;
                renderApiProducts();
                updateOverviewSupplier();
                if (force) showToast(`Catalogue ${result.supplier_name || "API"} actualisé`);
            } catch (error) {
                resellerCatalog = null;
                updateOverviewSupplier();
                document.getElementById("api-supplier-state").innerHTML = `
                    <div class="alert alert-error">
                        <span class="alert-icon">⚠️</span>
                        <span class="alert-message">${escapeHtml(error.message)}</span>
                    </div>`;
                document.getElementById("api-product-list").innerHTML = `
                    <div class="empty-state">
                        Cette API reste indisponible tant que sa clé n’est pas configurée sur le serveur.
                    </div>`;
            } finally {
                resellerCatalogLoading = false;
                if (refreshButton) refreshButton.disabled = false;
            }
        }

        function showApiWorkspaceStep(step, productId = null) {
            if (productId) selectedApiProductId = String(productId);
            apiWorkspaceStep = step;
            document.querySelectorAll(".api-step-button").forEach(button => {
                button.classList.toggle("active", button.dataset.apiStep === step);
            });
            document.querySelectorAll(".api-workspace-page").forEach(page => {
                page.classList.toggle("active", page.id === `api-workspace-${step}`);
            });
            if (step === "editor") renderApiProductEditor();
        }

        function openApiProductEditor(productId) {
            selectedApiProductId = String(productId);
            showApiWorkspaceStep("editor");
        }

        function renderApiProducts() {
            if (!resellerCatalog) return;
            const products = resellerCatalog.products || [];
            activeApiProvider = resellerCatalog.provider || activeApiProvider;
            document.getElementById("api-catalog-title").textContent =
                `Produits & services ${resellerCatalog.supplier_name || "API"}`;
            document.getElementById("api-supplier-state").innerHTML = `
                <div class="supplier-summary">
                    <div class="supplier-stat">
                        <span>Connexion fournisseur</span>
                        <strong><span class="live-dot"></span>Active</strong>
                    </div>
                    <div class="supplier-stat">
                        <span>Solde API</span>
                        <strong>${Number(resellerCatalog.balance || 0).toFixed(2)} ${escapeHtml(resellerCatalog.currency || "USDT")}</strong>
                    </div>
                    <div class="supplier-stat">
                        <span>Produits disponibles</span>
                        <strong>${products.length}</strong>
                    </div>
                    <div class="supplier-stat">
                        <span>Produits publiés</span>
                        <strong>${resellerCatalog.selected_count || 0}</strong>
                    </div>
                </div>`;

            const servicesStrip = document.getElementById("api-services-strip");
            const services = dashboardData.services || [];
            servicesStrip.innerHTML = services.length
                ? services.map(service => `
                    <span class="api-service-chip">${escapeHtml((service.emoji || "📦") + " " + service.name)}</span>
                `).join("")
                : '<span class="last-update">Aucun service créé.</span>';

            const list = document.getElementById("api-product-list");
            if (!products.length) {
                list.innerHTML = `<div class="empty-state">Aucun produit automatique disponible chez ${escapeHtml(resellerCatalog.supplier_name || "ce fournisseur")}.</div>`;
                return;
            }
            list.innerHTML = products.map(product => {
                const wholesale = Number(product.wholesale_price || 0);
                const retail = product.retail_price == null
                    ? Math.ceil((wholesale * 1.30) * 100) / 100
                    : Number(product.retail_price);
                return `
                    <article class="api-product-row ${product.enabled ? "enabled" : ""}"
                             data-enabled="${product.enabled ? "1" : "0"}"
                             data-stock="${Number(product.stock || 0)}"
                             data-search="${escapeHtml((product.name + " " + product.id + " " + (product.service_name || "")).toLowerCase())}">
                        <div>
                            <h3>${escapeHtml(product.name)}</h3>
                            <div class="api-product-id">${escapeHtml(product.id)}</div>
                            <div class="api-statuses" style="margin-top:8px;">
                                ${product.enabled ? '<span class="badge badge-paid">Publié</span>' : '<span class="badge">Brouillon</span>'}
                                ${product.manual_delivery ? '<span class="badge badge-pending">Livraison manuelle</span>' : ''}
                                <span class="badge badge-${product.stock > 0 ? "paid" : "cancelled"}">${Number(product.stock || 0)} stock</span>
                            </div>
                        </div>
                        <div class="api-row-stat">
                            <span>Service</span>
                            <strong>${escapeHtml(product.service_name ? (product.service_emoji || "📦") + " " + product.service_name : "Non assigné")}</strong>
                        </div>
                        <div class="api-row-stat">
                            <span>Grossiste</span>
                            <strong>${wholesale.toFixed(2)} ${escapeHtml(product.currency || "USDT")}</strong>
                        </div>
                        <div class="api-row-stat">
                            <span>Prix client</span>
                            <strong>${retail.toFixed(2)} ${escapeHtml(product.currency || "USDT")}</strong>
                        </div>
                        <button class="btn btn-primary" data-product-id="${escapeHtml(product.id)}"
                                onclick="openApiProductEditor(this.dataset.productId)">Configurer →</button>
                    </article>`;
            }).join("");
            filterApiProducts();
            if (apiWorkspaceStep === "editor") renderApiProductEditor();
        }

        function renderApiProductEditor() {
            const editor = document.getElementById("api-product-editor");
            const product = (resellerCatalog?.products || []).find(
                item => String(item.id) === String(selectedApiProductId)
            );
            if (!product) {
                editor.innerHTML = '<div class="empty-state">Choisissez d’abord un produit dans l’étape 2.</div>';
                return;
            }
            const wholesale = Number(product.wholesale_price || 0);
            const retail = product.retail_price == null
                ? Math.ceil((wholesale * 1.30) * 100) / 100
                : Number(product.retail_price);
            const profit = retail - wholesale;
            const margin = retail > 0 ? (profit / retail) * 100 : 0;
            const services = (dashboardData.services || []).map(service => `
                <option value="${Number(service.id)}" ${Number(product.service_id) === Number(service.id) ? "selected" : ""}>
                    ${escapeHtml((service.emoji || "📦") + " " + service.name)}
                </option>`).join("");
            const previewService = product.service_name
                ? `${product.service_emoji || "📦"} ${product.service_name}`
                : "📦 Choisissez un service";
            editor.innerHTML = `
                <article class="api-product-card ${product.enabled ? "enabled" : ""} ${product.published ? "published" : ""}"
                         data-product-id="${escapeHtml(product.id)}">
                    <div class="api-product-heading">
                        <div>
                            <div class="api-product-id">Configuration du produit</div>
                            <h3>${escapeHtml(product.name)}</h3>
                            <div class="api-product-id">${escapeHtml(product.id)}</div>
                        </div>
                        <div class="api-statuses">
                            ${product.enabled ? '<span class="badge badge-paid">Publié dans le bot</span>' : '<span class="badge">Brouillon</span>'}
                            ${product.manual_delivery ? '<span class="badge badge-pending">Livraison fournisseur manuelle</span>' : ''}
                            <span class="badge badge-${product.stock > 0 ? "paid" : "cancelled"}">${Number(product.stock || 0)} en stock</span>
                        </div>
                    </div>
                    <div class="api-price-grid">
                        <div class="api-price-box">
                            <span>Prix grossiste</span>
                            <strong>${wholesale.toFixed(2)} ${escapeHtml(product.currency || "USDT")}</strong>
                        </div>
                        <div class="api-price-box">
                            <span>Bénéfice par vente</span>
                            <strong class="api-profit ${profit <= 0 ? "loss" : ""}">${profit.toFixed(2)} ${escapeHtml(product.currency || "USDT")} · ${margin.toFixed(1)}%</strong>
                        </div>
                    </div>
                    <div class="api-config-grid">
                        <div class="form-group wide">
                            <label>Service affiché dans le bot</label>
                            <select class="api-service" onchange="toggleApiNewService(this); updateApiPreview(this)">
                                <option value="">Choisir un service…</option>
                                ${services}
                                <option value="__new__">＋ Créer un nouveau service</option>
                            </select>
                        </div>
                        <div class="api-new-service-fields wide">
                            <div class="form-group">
                                <label>Emoji</label>
                                <input class="api-service-emoji" maxlength="12" value="${escapeHtml(product.service_emoji || "📦")}" oninput="updateApiPreview(this)">
                            </div>
                            <div class="form-group">
                                <label>Nom du nouveau service</label>
                                <input class="api-new-service-name" maxlength="80" placeholder="Ex. Comptes Premium" oninput="updateApiPreview(this)">
                            </div>
                        </div>
                        <div class="form-group">
                            <label>Nom visible du produit</label>
                            <input class="api-display-name" maxlength="120" value="${escapeHtml(product.display_name || product.name)}" oninput="updateApiPreview(this)">
                        </div>
                        <div class="form-group">
                            <label>Votre prix client (${escapeHtml(product.currency || "USDT")})</label>
                            <input class="api-retail-price" type="number" min="${(wholesale + 0.01).toFixed(2)}"
                                   step="0.01" value="${retail.toFixed(2)}" oninput="updateApiProfit(this); updateApiPreview(this)">
                        </div>
                        <div class="form-group wide">
                            <label>Description client</label>
                            <textarea class="api-description" maxlength="1000" placeholder="Ce que le client reçoit…">${escapeHtml(product.custom_description || "")}</textarea>
                        </div>
                        <div class="form-group wide">
                            <label>Garantie affichée dans le bot</label>
                            <input class="api-warranty" maxlength="250" value="${escapeHtml(product.warranty || "")}" placeholder="Ex. Remplacement sous 24 heures">
                        </div>
                        <div class="form-group">
                            <label>Délai de livraison</label>
                            <input class="api-delivery-delay" maxlength="120" value="${escapeHtml(product.delivery_delay || "Instantané après confirmation")}">
                        </div>
                        <div class="form-group">
                            <label>Alerte stock bas</label>
                            <input class="api-low-stock" type="number" min="0" value="${Number(product.low_stock_threshold || 0)}">
                        </div>
                        <div class="form-group">
                            <label>Ordre d’affichage</label>
                            <input class="api-sort-order" type="number" min="0" value="${Number(product.sort_order || 0)}">
                        </div>
                        <div class="form-group">
                            <label>Référence fournisseur</label>
                            <input value="${escapeHtml(product.id)}" disabled>
                        </div>
                    </div>
                    <div class="api-product-preview">
                        <small>Aperçu dans le bot</small>
                        <div class="api-preview-service">${escapeHtml(previewService)}</div>
                        <div class="api-preview-line">
                            <span class="api-preview-product">${escapeHtml(product.display_name || product.name)}</span>
                            <span><span class="api-preview-price">${retail.toFixed(2)}</span> ${escapeHtml(product.currency || "USDT")}</span>
                        </div>
                    </div>
                    <div class="api-card-actions">
                        <label class="api-enabled-control">
                            <input class="api-enabled" type="checkbox" ${product.enabled ? "checked" : ""}>
                            Publier et revendre dans le bot
                        </label>
                        <button class="btn btn-primary" onclick="saveApiProduct(this)">Enregistrer & synchroniser</button>
                    </div>
                </article>`;
        }

        function toggleApiNewService(select) {
            select.closest(".api-product-card")
                .querySelector(".api-new-service-fields")
                .classList.toggle("visible", select.value === "__new__");
        }

        function updateApiPreview(input) {
            const card = input.closest(".api-product-card");
            const serviceSelect = card.querySelector(".api-service");
            const newService = serviceSelect.value === "__new__";
            const serviceText = newService
                ? `${card.querySelector(".api-service-emoji").value || "📦"} ${card.querySelector(".api-new-service-name").value || "Nouveau service"}`
                : (serviceSelect.selectedOptions[0]?.textContent.trim() || "📦 Choisissez un service");
            card.querySelector(".api-preview-service").textContent = serviceText;
            card.querySelector(".api-preview-product").textContent =
                card.querySelector(".api-display-name").value || "Produit";
            card.querySelector(".api-preview-price").textContent =
                Number(card.querySelector(".api-retail-price").value || 0).toFixed(2);
        }

        function updateApiProfit(input) {
            const card = input.closest(".api-product-card");
            const product = (resellerCatalog?.products || []).find(
                item => item.id === card.dataset.productId
            );
            if (!product) return;
            const profit = Number(input.value || 0) - Number(product.wholesale_price || 0);
            const output = card.querySelector(".api-profit");
            const retail = Number(input.value || 0);
            const margin = retail > 0 ? (profit / retail) * 100 : 0;
            output.textContent = `${profit.toFixed(2)} ${product.currency || "USDT"} · ${margin.toFixed(1)}%`;
            output.classList.toggle("loss", profit <= 0);
        }

        function filterApiProducts() {
            const search = (document.getElementById("api-product-search")?.value || "").toLowerCase();
            const visibility = document.getElementById("api-product-visibility")?.value || "";
            document.querySelectorAll(".api-product-row").forEach(card => {
                const matchesSearch = (card.dataset.search || "").includes(search);
                const matchesVisibility =
                    !visibility ||
                    (visibility === "enabled" && card.dataset.enabled === "1") ||
                    (visibility === "disabled" && card.dataset.enabled === "0") ||
                    (visibility === "stock" && Number(card.dataset.stock || 0) > 0);
                card.style.display = matchesSearch && matchesVisibility ? "" : "none";
            });
        }

        async function saveApiProduct(button) {
            const card = button.closest(".api-product-card");
            const retailInput = card.querySelector(".api-retail-price");
            const enabled = card.querySelector(".api-enabled").checked;
            const serviceSelect = card.querySelector(".api-service");
            if (!serviceSelect.value) {
                showToast("Choisissez un service pour publier ce produit.", "error");
                return;
            }
            if (serviceSelect.value === "__new__" && !card.querySelector(".api-new-service-name").value.trim()) {
                showToast("Donnez un nom au nouveau service.", "error");
                return;
            }
            const params = new URLSearchParams({
                action: "save_reseller_product",
                provider: activeApiProvider,
                product_id: card.dataset.productId,
                retail_price: retailInput.value,
                enabled: enabled ? "1" : "0",
                service_id: serviceSelect.value === "__new__" ? "" : serviceSelect.value,
                new_service_name: serviceSelect.value === "__new__" ? card.querySelector(".api-new-service-name").value : "",
                service_emoji: card.querySelector(".api-service-emoji").value,
                display_name: card.querySelector(".api-display-name").value,
                description: card.querySelector(".api-description").value,
                warranty: card.querySelector(".api-warranty").value,
                delivery_delay: card.querySelector(".api-delivery-delay").value,
                low_stock_threshold: card.querySelector(".api-low-stock").value,
                sort_order: card.querySelector(".api-sort-order").value
            });
            button.disabled = true;
            try {
                const response = await fetch("/admin", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded",
                        "X-Dashboard-Write-Token": dashboardWriteToken
                    },
                    body: params
                });
                const result = await response.json();
                if (!response.ok || !result.ok) throw new Error(result.error || "Enregistrement impossible.");
                resellerCatalog = null;
                await refreshDashboardData(true);
                showToast(enabled ? "Produit publié dans le catalogue du bot" : "Produit enregistré en brouillon");
                await loadApiProducts(true, activeApiProvider);
            } catch (error) {
                showToast(error.message, "error");
            } finally {
                button.disabled = false;
            }
        }

        function renderInventory() {
            const list = document.getElementById("inventory-list");
            list.innerHTML = "";

            let hasOffers = false;
            dashboardData.services.forEach(service => {
                if (service.offers && service.offers.length > 0) {
                    hasOffers = true;
                    const card = document.createElement("div");
                    card.className = "service-card";
                    card.innerHTML = `
                        <div class="service-header">
                            <div class="service-title">
                                <span style="font-size:24px;">${service.emoji}</span>
                                <h3>${service.name}</h3>
                            </div>
                        </div>
                        <div class="offers-list" id="inv-offers-for-service-${service.id}"></div>
                    `;
                    list.appendChild(card);

                    const offersListContainer = card.querySelector(`#inv-offers-for-service-${service.id}`);
                    service.offers.forEach(offer => {
                        const row = document.createElement("div");
                        row.className = "offer-row";
                        row.innerHTML = `
                            <div class="offer-info">
                                <div class="offer-name">${offer.name}</div>
                                ${offer.description ? `<div style="color:var(--text-muted);font-size:13px;margin-bottom:6px;">${escapeHtml(offer.description)}</div>` : ''}
                                <div class="offer-meta">
                                    <span>📦 Dispo : ${offer.stock}</span>
                                </div>
                            </div>
                            <div class="offer-actions">
                                <button class="btn btn-primary" style="padding:6px 12px; font-size:12px;" onclick="openAddInventoryModal(${offer.id})">🔐 Ajouter des codes</button>
                            </div>
                        `;
                        offersListContainer.appendChild(row);
                    });
                }
            });

            if (!hasOffers) {
                list.innerHTML = `<div class="empty-state">Créez d'abord des offres dans le catalogue.</div>`;
            }
        }

        function renderInventoryItems() {
            const tbody = document.querySelector("#inventory-table tbody");
            tbody.innerHTML = "";
            const items = dashboardData.inventory || [];
            if (!items.length) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Aucune référence pour ces filtres.</td></tr>';
                return;
            }
            items.forEach(item => {
                const tr = document.createElement("tr");
                const linkedOrder = item.reserved_order_id || item.delivered_order_id || "—";
                const canToggle = ["available", "disabled"].includes(item.status);
                tr.innerHTML = `
                    <td><code>#${item.reference_id}</code></td>
                    <td>#${item.offer_id}</td>
                    <td><code>${escapeHtml(item.masked_preview || "***")}</code></td>
                    <td><span class="badge badge-${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></td>
                    <td>${linkedOrder === "—" ? linkedOrder : "#" + linkedOrder}</td>
                    <td>
                        <button class="btn btn-secondary" style="padding:6px 10px" onclick="revealInventory(${item.reference_id}, this)">👁 Révéler</button>
                        ${canToggle ? `<button class="btn ${item.status === 'disabled' ? 'btn-primary' : 'btn-danger'}" style="padding:6px 10px" onclick="toggleInventory(${item.reference_id}, ${item.status === 'disabled' ? 0 : 1})">${item.status === 'disabled' ? 'Activer' : 'Désactiver'}</button>` : ''}
                    </td>`;
                tbody.appendChild(tr);
            });
        }

        function filterInventoryItems() {
            clearTimeout(inventoryFilterTimer);
            inventoryPagination.page = 1;
            inventoryFilterTimer = setTimeout(refreshDashboardData, 250);
        }

        async function changeInventoryPage(delta) {
            const next = Math.max(1, Math.min(inventoryPagination.pages || 1, inventoryPagination.page + delta));
            if (next === inventoryPagination.page) return;
            inventoryPagination.page = next;
            await refreshDashboardData();
        }

        function updateInventoryPagination() {
            const pages = inventoryPagination.pages || 1;
            document.getElementById("inventory-page-label").textContent = `Page ${inventoryPagination.page} / ${pages} (${inventoryPagination.total || 0})`;
            document.getElementById("inventory-prev").disabled = inventoryPagination.page <= 1;
            document.getElementById("inventory-next").disabled = inventoryPagination.page >= pages;
        }

        async function revealInventory(itemId, button) {
            if (!confirm("Afficher temporairement le contenu complet de cette référence ?")) return;
            const params = new URLSearchParams({ action: "reveal_inventory", inventory_id: itemId });
            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: params
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || "Révélation impossible");
                const original = button.textContent;
                button.textContent = data.value;
                button.disabled = true;
                setTimeout(() => { button.textContent = original; button.disabled = false; }, 15000);
            } catch (err) {
                showToast(err.message || "Erreur réseau", "error");
            }
        }

        async function toggleInventory(itemId, disabled) {
            if (!confirm("Confirmer le changement d'état de cette référence ?")) return;
            const params = new URLSearchParams({ action: "toggle_inventory", inventory_id: itemId, disabled });
            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: params
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || "Action impossible");
                showToast("Inventaire mis à jour");
                await refreshDashboardData();
            } catch (err) {
                showToast(err.message || "Erreur réseau", "error");
            }
        }

        function renderTicketsTable() {
            const tbody = document.querySelector("#tickets-table tbody");
            tbody.innerHTML = "";

            if (!dashboardData.tickets || dashboardData.tickets.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Aucun ticket support.</td></tr>';
                return;
            }

            dashboardData.tickets.forEach(ticket => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>#${ticket.id}</td>
                    <td>${formatDateTime(ticket.created_at)}</td>
                    <td><code>${ticket.user_id}</code></td>
                    <td>${ticket.category || 'Général'}</td>
                    <td><span class="badge badge-${ticket.status}">${ticket.status}</span></td>
                    <td>
                        <button class="btn btn-secondary" style="padding:6px 12px; font-size:12px;" onclick="viewTicket(${ticket.id})">💬 Ouvrir</button>
                        ${ticket.status !== 'closed' ? `<button class="btn btn-danger" style="padding:6px 12px; font-size:12px;" onclick="closeTicket(${ticket.id})">Fermer</button>` : ''}
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        function renderInteractions() {
            const data = dashboardData.interactions || {};
            const summary = data.summary || {};
            const kpis = [
                ["Total interactions", summary.total || 0],
                ["Aujourd’hui", summary.today || 0],
                ["Utilisateurs actifs", summary.active_today || 0],
                ['<span class="live-dot"></span>Actifs (5 min)', summary.live_users || 0],
                ["Clics boutons (30 j)", summary.button_clicks || 0],
                ["Messages (30 j)", summary.messages || 0],
            ];
            document.getElementById("interaction-kpis").innerHTML = kpis.map(item =>
                `<div class="interaction-kpi"><span>${item[0]}</span><strong>${item[1]}</strong></div>`
            ).join("");

            const daily = data.daily || [];
            const maxDaily = Math.max(1, ...daily.map(item => item.count || 0));
            document.getElementById("interactions-daily-chart").innerHTML = daily.map(item => {
                const height = Math.max(2, Math.round((item.count || 0) / maxDaily * 145));
                return `<div class="daily-bar-wrap" title="${item.date}: ${item.count}">
                    <span style="font-size:10px">${item.count || ""}</span>
                    <div class="daily-bar" style="height:${height}px"></div>
                    <span class="daily-label">${item.date.slice(5)}</span>
                </div>`;
            }).join("");

            const types = data.types || {};
            const typeEntries = Object.entries(types).sort((a,b) => b[1] - a[1]);
            const maxType = Math.max(1, ...typeEntries.map(item => item[1]));
            document.getElementById("interactions-type-chart").innerHTML = typeEntries.length
                ? typeEntries.map(([type, count]) => `<div class="type-row">
                    <div class="type-row-head"><span>${escapeHtml(type)}</span><strong>${count}</strong></div>
                    <div class="type-track"><div class="type-fill" style="width:${count / maxType * 100}%"></div></div>
                </div>`).join("")
                : '<div class="empty-state">Aucune interaction enregistrée.</div>';

            const serviceClicks = data.service_clicks || {};
            const serviceDays = [...(serviceClicks.daily || [])].reverse();
            const serviceTotal = serviceClicks.total || 0;
            const serviceCount = (serviceClicks.services || []).length;
            document.getElementById("service-clicks-summary").textContent =
                `${serviceTotal} clic${serviceTotal === 1 ? "" : "s"} • ${serviceCount} service${serviceCount === 1 ? "" : "s"}`;
            const maxServiceClicks = Math.max(
                1,
                ...serviceDays.flatMap(day => (day.services || []).map(service => service.count || 0)),
            );
            document.getElementById("service-clicks-daily").innerHTML = serviceDays.length
                ? serviceDays.map(day => {
                    const label = new Date(`${day.date}T00:00:00Z`).toLocaleDateString(
                        "fr-FR", {weekday:"short", day:"2-digit", month:"short", timeZone:"UTC"},
                    );
                    const rows = (day.services || []).map(service => {
                        const width = Math.max(4, Math.round((service.count || 0) / maxServiceClicks * 100));
                        return `<div class="service-click-row" title="${escapeHtml(service.name || "Service")}: ${service.count || 0}">
                            <span class="service-click-name">${escapeHtml(service.name || `Service #${service.service_id}`)}</span>
                            <span class="service-click-track"><span class="service-click-fill" style="display:block;width:${width}%"></span></span>
                            <span class="service-click-count">${service.count || 0}</span>
                        </div>`;
                    }).join("");
                    return `<article class="service-click-day">
                        <div class="service-click-day-head"><strong>${escapeHtml(label)}</strong><span>${day.total || 0} clic${day.total === 1 ? "" : "s"}</span></div>
                        ${rows}
                    </article>`;
                }).join("")
                : '<div class="empty-state">Aucun clic sur un service pendant cette période.</div>';

            const tbody = document.querySelector("#interactions-table tbody");
            const events = data.events || [];
            tbody.innerHTML = events.length ? events.map(event => {
                const content = event.content || event.screen || "";
                const search = [
                    event.full_name, event.first_name, event.username, event.user_id,
                    event.interaction_type, event.action, content
                ].join(" ").toLowerCase();
                const day = new Date((event.created_at || 0) * 1000).toISOString().slice(0,10);
                return `<tr data-search="${escapeHtml(search)}" data-type="${escapeHtml(event.interaction_type || "")}" data-day="${day}">
                    <td>${formatDateTime(event.created_at)}</td>
                    <td>${escapeHtml(event.full_name || event.first_name || "—")}</td>
                    <td>${event.username ? "@" + escapeHtml(event.username) : "—"}</td>
                    <td><code>${event.user_id || "—"}</code></td>
                    <td><span class="badge badge-info">${escapeHtml(event.interaction_type || "other")}</span></td>
                    <td><code>${escapeHtml(event.action || "—")}</code></td>
                    <td class="interaction-content">${escapeHtml(content || "—")}</td>
                </tr>`;
            }).join("") : '<tr><td colspan="7" class="empty-state">Aucune interaction disponible.</td></tr>';
            filterInteractions();
        }

        function filterInteractions() {
            const search = (document.getElementById("interaction-search")?.value || "").toLowerCase();
            const type = document.getElementById("interaction-type")?.value || "";
            const day = document.getElementById("interaction-date")?.value || "";
            document.querySelectorAll("#interactions-table tbody tr").forEach(row => {
                if (!row.dataset.search) return;
                const visible = (!search || row.dataset.search.includes(search))
                    && (!type || row.dataset.type === type)
                    && (!day || row.dataset.day === day);
                row.style.display = visible ? "" : "none";
            });
        }

        function renderAuditTable() {
            const tbody = document.querySelector("#audit-table tbody");
            tbody.innerHTML = "";

            if (!dashboardData.audits || dashboardData.audits.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" class="empty-state">Aucun événement d'audit disponible.</td></tr>`;
                return;
            }

            dashboardData.audits.forEach(audit => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${formatDateTime(audit.created_at)}</td>
                    <td><code>${audit.action}</code></td>
                    <td>${audit.actor_id || 'système'}</td>
                    <td><code>${JSON.stringify(audit.details || {})}</code></td>
                `;
                tbody.appendChild(tr);
            });
        }

        function fillSettingsForm() {
            document.getElementById("shop-name-input").value = dashboardData.shop_name || "BlackMarket";
            document.getElementById("currency-input").value = dashboardData.currency || "USDT";
            document.getElementById("low-stock-input").value = dashboardData.low_stock_threshold || 5;
            document.getElementById("expiry-input").value = dashboardData.order_expiry_seconds || 1800;
            document.getElementById("payment-recipient-input").value = dashboardData.payment_recipient || "";
            document.getElementById("affiliate-enabled-input").checked = dashboardData.affiliate_enabled !== false;
            document.getElementById("affiliate-target-input").value = dashboardData.affiliate_target || 10;
            document.getElementById("affiliate-reward-input").value = dashboardData.affiliate_reward_cents || 100;
            document.getElementById("maintenance-enabled-input").checked = dashboardData.maintenance_enabled === true;
            document.getElementById("maintenance-message-input").value = dashboardData.maintenance_message || "";
            document.getElementById("welcome-message-input").value = dashboardData.welcome_message || "";
            document.getElementById("help-message-input").value = dashboardData.help_message || "";
            document.getElementById("terms-message-input").value = dashboardData.terms_message || "";
            document.getElementById("privacy-message-input").value = dashboardData.privacy_message || "";
            document.getElementById("active-languages-input").value = dashboardData.active_languages || "en,ar";
            if (document.getElementById("announcement-new-stock-input")) document.getElementById("announcement-new-stock-input").value = dashboardData.announcement_new_stock || "";
            if (document.getElementById("announcement-flash-sale-input")) document.getElementById("announcement-flash-sale-input").value = dashboardData.announcement_flash_sale || "";
            if (document.getElementById("announcement-restock-input")) document.getElementById("announcement-restock-input").value = dashboardData.announcement_restock || "";
        }

        // Actions Ajax
        async function checkAndRepairTelegram() {
            const button = document.getElementById("telegram-repair-button");
            const originalText = button.textContent;
            button.disabled = true;
            button.textContent = "Vérification...";
            try {
                const healthResponse = await fetch("/admin/api/telegram-health", {
                    headers: { "Accept": "application/json" }
                });
                const health = await healthResponse.json();
                if (!healthResponse.ok || !health.ok) {
                    showToast(health.message || "Telegram est temporairement indisponible", "error");
                    return;
                }
                if (health.healthy) {
                    showToast(`Webhook Telegram actif · ${health.pending_update_count || 0} mise(s) à jour en attente`);
                    return;
                }
                const reason = health.last_error_message
                    ? `Dernière erreur : ${health.last_error_message}`
                    : "L’URL Telegram ne correspond pas à l’URL stable.";
                if (!confirm(`${reason}\n\nRéparer le webhook maintenant ?`)) return;
                button.textContent = "Réparation...";
                const params = new URLSearchParams({ action: "repair_telegram_webhook" });
                const repairResponse = await fetch("/admin", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded",
                        "X-Dashboard-Write-Token": dashboardWriteToken
                    },
                    body: params
                });
                const repair = await repairResponse.json();
                if (!repairResponse.ok || !repair.ok) {
                    showToast(repair.message || "Réparation Telegram impossible", "error");
                    return;
                }
                showToast("Webhook Telegram réparé sur l’URL stable");
            } catch (err) {
                showToast("Impossible de contacter Telegram depuis Railway", "error");
            } finally {
                button.disabled = false;
                button.textContent = originalText;
            }
        }

        async function testBinanceConnection() {
            const button = document.getElementById("binance-test-button");
            const originalText = button.textContent;
            button.disabled = true;
            button.textContent = "Test en cours...";
            try {
                const response = await fetch("/admin/api/binance-health", {
                    headers: { "Accept": "application/json" }
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    showToast(result.message || "Connexion Binance indisponible", "error");
                    return;
                }
                const endpoint = new URL(result.endpoint).hostname;
                showToast(`Binance connecté via ${endpoint} · ${result.transactions_24h} transaction(s) sur 24 h`);
            } catch (err) {
                showToast("Impossible de tester Binance depuis Railway", "error");
            } finally {
                button.disabled = false;
                button.textContent = originalText;
            }
        }

        async function testBybitConnection() {
            const button = document.getElementById("bybit-test-button");
            const originalText = button.textContent;
            button.disabled = true;
            button.textContent = "Test en cours...";
            try {
                const response = await fetch("/admin/api/bybit-health", {
                    headers: { "Accept": "application/json" }
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    showToast(result.message || "Connexion Bybit indisponible", "error");
                    return;
                }
                const endpoint = new URL(result.endpoint).hostname;
                showToast(`Bybit connecté via ${endpoint} · ${result.transactions} transaction(s) récente(s)`);
            } catch (err) {
                showToast("Impossible de tester Bybit depuis Railway", "error");
            } finally {
                button.disabled = false;
                button.textContent = originalText;
            }
        }

        async function refreshDashboardData(silent = false) {
            if (realtimeRequestRunning) return;
            realtimeRequestRunning = true;
            showProgress();
            try {
                const status = document.getElementById("order-filter-status")?.value || "";
                const search = document.getElementById("order-search")?.value || "";
                const query = new URLSearchParams({ page: ordersPagination.page, per_page: 25 });
                if (status) query.set("status", status);
                if (search) query.set("search", search);
                const dateFrom = document.getElementById("order-date-from")?.value || "";
                const dateTo = document.getElementById("order-date-to")?.value || "";
                const sort = document.getElementById("order-sort")?.value || "date";
                if (dateFrom) query.set("date_from", dateFrom);
                if (dateTo) query.set("date_to", dateTo + "T23:59:59");
                query.set("sort", sort);
                const inventoryQuery = new URLSearchParams({ page: inventoryPagination.page, per_page: 25 });
                const inventoryStatus = document.getElementById("inventory-filter-status")?.value || "";
                const inventorySearch = document.getElementById("inventory-search")?.value || "";
                if (inventoryStatus) inventoryQuery.set("status", inventoryStatus);
                if (inventorySearch) inventoryQuery.set("search", inventorySearch);
                const [res, ordersRes, customersRes, ticketsRes, inventoryRes] = await Promise.all([
                    fetch("/admin/api/data"),
                    fetch("/admin/api/orders?" + query.toString()),
                    fetch("/admin/api/customers?per_page=100"),
                    fetch("/admin/api/tickets?per_page=100"),
                    fetch("/admin/api/inventory?" + inventoryQuery.toString())
                ]);
                if (res.ok && ordersRes.ok && customersRes.ok && ticketsRes.ok && inventoryRes.ok) {
                    const previousSnapshot = notificationSnapshot;
                    dashboardData = await res.json();
                    const orderData = await ordersRes.json();
                    const customerData = await customersRes.json();
                    const ticketData = await ticketsRes.json();
                    const inventoryData = await inventoryRes.json();
                    dashboardData.orders = orderData.items;
                    dashboardData.users = customerData.items;
                    dashboardData.tickets = ticketData.items;
                    dashboardData.inventory = inventoryData.items;
                    inventoryPagination = inventoryData;
                    ordersPagination = orderData;
                    notificationSnapshot = snapshotDashboard(dashboardData);
                    detectDashboardEvents(previousSnapshot, notificationSnapshot);
                    refreshUI();
                    hideProgress();
                    setRealtimeStatus(true);
                    updateOrdersPagination();
                    updateInventoryPagination();
                    if (!silent) showToast("Données actualisées");
                } else {
                    setRealtimeStatus(false);
                    if (!silent) showToast("Échec de l'actualisation des données", "error");
                }
            } catch (err) {
                setRealtimeStatus(false);
                hideProgress();
                if (!silent) showToast("Erreur réseau lors de l'actualisation", "error");
            } finally {
                realtimeRequestRunning = false;
            }
        }

        async function changeOrdersPage(delta) {
            const next = Math.max(1, Math.min(ordersPagination.pages || 1, ordersPagination.page + delta));
            if (next === ordersPagination.page) return;
            ordersPagination.page = next;
            await refreshDashboardData();
        }

        function updateOrdersPagination() {
            const pages = ordersPagination.pages || 1;
            document.getElementById("orders-page-label").textContent = `Page ${ordersPagination.page} / ${pages} (${ordersPagination.total || 0})`;
            document.getElementById("orders-prev").disabled = ordersPagination.page <= 1;
            document.getElementById("orders-next").disabled = ordersPagination.page >= pages;
        }

        async function handleFormSubmit(event, action) {
            event.preventDefault();
            const form = event.target;
            const formData = new FormData(form);
            const params = new URLSearchParams();
            params.append("action", action);
            for (const pair of formData.entries()) {
                params.append(pair[0], pair[1]);
            }

            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: params
                });
                if (res.ok) {
                    showToast("Opération réussie");
                    closeModal(form.closest('.modal').id);
                    form.reset();
                    await refreshDashboardData();
                } else {
                    const err = await res.json();
                    showToast(err.error || "Erreur de traitement", "error");
                }
            } catch (err) {
                showToast("Erreur réseau", "error");
            }
        }

        async function toggleBanUser(userId, banned) {
            if (!confirm(`Voulez-vous vraiment ${banned ? 'bannir' : 'débannir'} l'utilisateur ${userId} ?`)) return;
            const params = new URLSearchParams();
            params.append("action", "toggle_ban");
            params.append("user_id", userId);
            params.append("banned", banned);

            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: params
                });
                if (res.ok) {
                    showToast("Statut utilisateur mis à jour");
                    await refreshDashboardData();
                }
            } catch (err) {
                showToast("Erreur réseau", "error");
            }
        }

        async function toggleService(serviceId, active) {
            const params = new URLSearchParams();
            params.append("action", "toggle_service");
            params.append("service_id", serviceId);

            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: params
                });
                if (res.ok) {
                    showToast("Statut service mis à jour");
                    await refreshDashboardData();
                }
            } catch (err) {
                showToast("Erreur réseau", "error");
            }
        }

        async function offerAction(action, offerId, confirmation) {
            if (confirmation && !confirm(confirmation)) return;
            const params = new URLSearchParams({ action, offer_id: offerId });
            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: params
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || "Action impossible");
                showToast("Offre mise à jour");
                await refreshDashboardData();
            } catch (err) {
                showToast(err.message || "Erreur réseau", "error");
            }
        }

        function toggleOffer(offerId) {
            return offerAction("toggle_offer", offerId);
        }

        function duplicateOffer(offerId) {
            return offerAction("duplicate_offer", offerId, "Dupliquer cette offre sans copier son inventaire ?");
        }

        function openAddOfferModal(serviceId = null) {
            const select = document.getElementById("add-offer-service-id");
            const services = dashboardData.services || [];
            select.innerHTML = services.length
                ? services.map(service => `<option value="${service.id}">${escapeHtml(service.name)}</option>`).join("")
                : '<option value="">Catalogue par defaut</option>';
            if (serviceId !== null) select.value = String(serviceId);
            openModal("add-offer-modal");
        }

        function openEditOfferModal(offerId) {
            const offer = (dashboardData.services || [])
                .flatMap(service => service.offers || [])
                .find(item => item.id === offerId);
            if (!offer) {
                showToast("Offre introuvable", "error");
                return;
            }
            document.getElementById("edit-offer-id").value = offer.id;
            document.getElementById("edit-offer-name").value = offer.name || "";
            document.getElementById("edit-offer-description").value = offer.description || "";
            document.getElementById("edit-offer-period-days").value = offer.period_days || 30;
            document.getElementById("edit-offer-warranty-days").value = offer.warranty_days ?? (offer.note === "NW" ? 0 : (Number((offer.note || "").match(/\\d+/)?.[0]) || 0));
            document.getElementById("edit-offer-price").value = offer.price ?? 0;
            document.getElementById("edit-offer-bulk-quantity").value = offer.bulk_quantity ?? 0;
            document.getElementById("edit-offer-bulk-price").value = offer.bulk_unit_price ?? "";
            document.getElementById("edit-offer-sort").value = offer.sort_order ?? 0;
            document.getElementById("edit-offer-delay").value = offer.delivery_delay || "";
            document.getElementById("edit-offer-threshold").value = offer.low_stock_threshold ?? 5;
            document.getElementById("edit-offer-auto").checked = offer.auto_delivery !== false;
            openModal("edit-offer-modal");
        }

        function openAddInventoryModal(offerId) {
            document.getElementById("add-inventory-offer-id").value = offerId;
            openModal("add-inventory-modal");
        }

        function escapeHtml(value) {
            const node = document.createElement("div");
            node.textContent = value == null ? "" : String(value);
            return node.innerHTML;
        }

        async function viewCustomer(userId) {
            try {
                const res = await fetch(`/admin/api/customers?user_id=${userId}`);
                const customer = await res.json();
                if (!res.ok) throw new Error(customer.error || "Client introuvable");
                const orders = (customer.orders || []).map(order =>
                    `<li>#${order.id} — ${escapeHtml(order.offer_name || '')} — ${escapeHtml(order.status || '')}</li>`
                ).join("") || "<li>Aucune commande</li>";
                const tickets = (customer.tickets || []).map(ticket =>
                    `<li>#${ticket.id} — ${escapeHtml(ticket.category || 'other')} — ${escapeHtml(ticket.status || '')}</li>`
                ).join("") || "<li>Aucun ticket</li>";
                document.getElementById("customer-detail-body").innerHTML = `
                    <div class="detail-grid">
                        <div><strong>Telegram ID :</strong> <code>${customer.telegram_id}</code></div>
                        <div><strong>Username :</strong> ${escapeHtml(customer.username ? '@' + customer.username : '—')}</div>
                        <div><strong>Prénom :</strong> ${escapeHtml(customer.first_name || '—')}</div>
                        <div><strong>Langue :</strong> ${escapeHtml(customer.lang || 'en')}</div>
                        <div><strong>Portefeuille :</strong> ${Number(customer.wallet_balance || 0).toFixed(2)} ${escapeHtml(dashboardData.currency)}</div>
                        <div><strong>Inscrit le :</strong> ${customer.created_at ? formatDateTime(customer.created_at) : '—'}</div>
                        <div><strong>Dernière activité :</strong> ${customer.last_active_at ? formatDateTime(customer.last_active_at) : 'Jamais'}</div>
                        <div><strong>Interactions :</strong> ${customer.interaction_count || 0}</div>
                        <div><strong>Commandes :</strong> ${customer.order_count || 0}</div>
                        <div><strong>Payées :</strong> ${customer.paid_order_count || 0}</div>
                        <div><strong>Total dépensé :</strong> ${(customer.total_spent || 0).toFixed(2)} ${escapeHtml(dashboardData.currency)}</div>
                        <div><strong>Filleuls :</strong> ${customer.referral_count || 0}</div>
                    </div>
                    <div class="service-card" style="margin:18px 0;">
                        <h4 style="margin-bottom:12px;">Gérer le portefeuille</h4>
                        <form onsubmit="adjustCustomerWallet(event, ${customer.telegram_id})" style="display:grid;grid-template-columns:minmax(140px,180px) 1fr auto;gap:10px;align-items:end;">
                            <div class="form-group" style="margin:0;">
                                <label>Montant (${escapeHtml(dashboardData.currency)})</label>
                                <input name="amount" type="number" step="0.01" min="-10000" max="10000" required placeholder="+10 ou -5">
                            </div>
                            <div class="form-group" style="margin:0;">
                                <label>Motif</label>
                                <input name="reason" maxlength="500" placeholder="Bonus, correction, remboursement...">
                            </div>
                            <button class="btn btn-primary" type="submit">Appliquer</button>
                        </form>
                        <p class="muted" style="margin-top:8px;">Montant positif pour créditer, négatif pour débiter. Le solde ne peut pas devenir négatif.</p>
                    </div>
                    <h4>Commandes récentes</h4><ul>${orders}</ul>
                    <h4>Tickets</h4><ul>${tickets}</ul>`;
                openModal("customer-detail-modal");
            } catch (err) {
                showToast(err.message || "Erreur réseau", "error");
            }
        }

        async function adjustCustomerWallet(event, userId) {
            event.preventDefault();
            const form = event.target;
            const amount = Number(form.elements.amount.value);
            if (!Number.isFinite(amount) || amount === 0 || Math.abs(amount) > 10000) {
                showToast("Saisissez un montant valide entre -10 000 et 10 000", "error");
                return;
            }
            const verb = amount > 0 ? "créditer" : "débiter";
            if (!confirm(`Confirmer : ${verb} ${Math.abs(amount).toFixed(2)} ${dashboardData.currency} pour l'utilisateur ${userId} ?`)) return;
            const params = new URLSearchParams({
                action: "adjust_user_wallet",
                user_id: userId,
                amount: amount.toFixed(2),
                reason: form.elements.reason.value || "",
            });
            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded",
                        "X-Dashboard-Write-Token": dashboardWriteToken,
                    },
                    body: params,
                });
                const payload = await res.json();
                if (!res.ok || !payload.ok) throw new Error(payload.error || "Modification impossible");
                showToast(`Nouveau solde : ${Number(payload.balance).toFixed(2)} ${dashboardData.currency}`);
                closeModal("customer-detail-modal");
                await refreshDashboardData();
            } catch (err) {
                showToast(err.message || "Erreur réseau", "error");
            }
        }

        async function viewOrderDetail(orderId) {
            const order = dashboardData.orders.find(o => o.id === orderId);
            if (!order) return;

            const body = document.getElementById("order-detail-body");
            const statusOptions = ORDER_STATUSES.map(status =>
                `<option value="${status}" ${status === order.status ? "selected" : ""}>${status}</option>`
            ).join("");
            body.innerHTML = `
                <div style="display:flex; flex-direction:column; gap:16px;">
                    <div><strong>ID Commande:</strong> #${order.id}</div>
                    <div><strong>Date:</strong> ${formatDateTime(order.created_at)}</div>
                    <div><strong>Client (Telegram ID):</strong> <code>${order.user_id}</code></div>
                    <div><strong>Produit:</strong> ${escapeHtml(order.service_name || "")} - ${escapeHtml(order.offer_name || "")}</div>
                    <div><strong>Verification:</strong> <code>${escapeHtml(order.verify_method || "-")}</code></div>
                    <form id="order-admin-form" onsubmit="updateOrderAdmin(event, ${order.id})" style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px;">
                        <div class="form-group"><label>Statut</label><select name="status">${statusOptions}</select></div>
                        <div class="form-group"><label>TXID</label><input name="txid" value="${escapeHtml(order.txid || "")}" placeholder="Transaction ID"></div>
                        <div class="form-group"><label>Quantite</label><input type="number" min="1" name="qty" value="${order.qty || 1}"></div>
                        <div class="form-group"><label>Prix unitaire</label><input type="number" min="0" step="0.01" name="unit_price" value="${order.unit_price ?? 0}"></div>
                        <div class="form-group"><label>Total</label><input type="number" min="0" step="0.01" name="total_price" value="${order.total_price ?? 0}"></div>
                        <div class="form-group" style="grid-column:1 / -1;"><label>Notes admin</label><textarea name="admin_note" id="order-admin-note" rows="3" placeholder="Notes optionnelles...">${escapeHtml(order.admin_note || "")}</textarea></div>
                        <button class="btn btn-primary" type="submit">Enregistrer la commande</button>
                    </form>
                    <div class="form-group">
                        <label>Livraison manuelle</label>
                        <textarea id="manual-delivery-text" rows="4" placeholder="Contenu a envoyer au client...">${escapeHtml(order.delivery_text || "")}</textarea>
                        <button class="btn btn-primary" style="margin-top:8px;" onclick="manualDeliverOrder(${order.id})">Livrer manuellement</button>
                    </div>
                    <div style="display:flex; flex-wrap:wrap; gap:12px; margin-top:12px;">
                        ${order.status === 'awaiting_verification' || order.status === 'pending_payment' || order.status === 'manual_review' ? `
                            <button class="btn btn-primary" onclick="confirmPaymentManual(${order.id})">Confirmer paiement</button>
                        ` : ''}
                        ${order.status !== 'cancelled' && order.status !== 'refunded' ? `
                            <button class="btn btn-danger" onclick="cancelOrder(${order.id})">Annuler commande</button>
                        ` : ''}
                        ${['awaiting_verification', 'verification_failed', 'manual_review'].includes(order.status) ? `
                            <button class="btn btn-secondary" onclick="orderAction('reset_order', ${order.id})">Remettre en attente</button>
                        ` : ''}
                        ${['paid', 'payment_confirmed', 'preparing_delivery', 'delivered', 'manual_review'].includes(order.status) ? `
                            <button class="btn btn-danger" onclick="orderAction('refund_order', ${order.id}, true)">Rembourser</button>
                        ` : ''}
                        ${order.status === 'delivered' ? `
                            <button class="btn btn-secondary" onclick="orderAction('resend_delivery', ${order.id})">Renvoyer la livraison auto</button>
                        ` : ''}
                        <button class="btn btn-secondary" onclick="messageCustomer(${order.id})">Ecrire au client</button>
                    </div>
                </div>
            `;
            openModal("order-detail-modal");
        }
        async function confirmPaymentManual(orderId) {
            if (!confirm("Confirmer manuellement le paiement de cette commande ?")) return;
            const params = new URLSearchParams();
            params.append("action", "confirm_payment");
            params.append("order_id", orderId);

            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: params
                });
                if (res.ok) {
                    showToast("Paiement validé");
                    closeModal("order-detail-modal");
                    await refreshDashboardData();
                }
            } catch (err) {
                showToast("Erreur réseau", "error");
            }
        }

        async function updateOrderAdmin(event, orderId) {
            event.preventDefault();
            const formData = new FormData(event.target);
            const params = new URLSearchParams();
            params.append("action", "update_order_admin");
            params.append("order_id", orderId);
            for (const pair of formData.entries()) {
                params.append(pair[0], pair[1]);
            }

            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: params
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || "Mise a jour impossible");
                showToast("Commande mise a jour");
                closeModal("order-detail-modal");
                await refreshDashboardData();
            } catch (err) {
                showToast(err.message || "Erreur reseau", "error");
            }
        }

        async function manualDeliverOrder(orderId) {
            const content = document.getElementById("manual-delivery-text").value.trim();
            if (!content) {
                showToast("Ajoute le contenu de livraison", "error");
                return;
            }
            if (!confirm("Livrer cette commande et envoyer le contenu au client ?")) return;

            const params = new URLSearchParams({
                action: "manual_deliver_order",
                order_id: orderId,
                delivery_text: content
            });
            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: params
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || "Livraison impossible");
                showToast("Commande livree");
                closeModal("order-detail-modal");
                await refreshDashboardData();
            } catch (err) {
                showToast(err.message || "Erreur reseau", "error");
            }
        }

        async function cancelOrder(orderId) {
            const reason = prompt("Raison de l'annulation :");
            if (reason === null) return;
            const params = new URLSearchParams();
            params.append("action", "cancel_order");
            params.append("order_id", orderId);
            params.append("reason", reason);

            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: params
                });
                if (res.ok) {
                    showToast("Commande annulée");
                    closeModal("order-detail-modal");
                    await refreshDashboardData();
                }
            } catch (err) {
                showToast("Erreur réseau", "error");
            }
        }

        async function orderAction(action, orderId, askReason = false) {
            if (!confirm("Confirmer cette action sur la commande #" + orderId + " ?")) return;
            const params = new URLSearchParams({ action, order_id: orderId });
            if (askReason) params.append("reason", prompt("Motif (optionnel) :") || "");
            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: params
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || "Action impossible");
                showToast("Action effectuée avec succès");
                closeModal("order-detail-modal");
                await refreshDashboardData();
            } catch (err) {
                showToast(err.message || "Erreur réseau", "error");
            }
        }

        async function messageCustomer(orderId) {
            const message = prompt("Message à envoyer au client :");
            if (!message) return;
            const params = new URLSearchParams({ action: "message_customer", order_id: orderId, message });
            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: params
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || "Envoi impossible");
                showToast("Message envoyé au client");
            } catch (err) {
                showToast(err.message || "Erreur réseau", "error");
            }
        }

        async function saveOrderNote(orderId) {
            const note = document.getElementById("order-admin-note").value;
            const params = new URLSearchParams();
            params.append("action", "save_order_note");
            params.append("order_id", orderId);
            params.append("note", note);

            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: params
                });
                if (res.ok) {
                    showToast("Notes enregistrées");
                    closeModal("order-detail-modal");
                    await refreshDashboardData();
                }
            } catch (err) {
                showToast("Erreur réseau", "error");
            }
        }

        async function viewTicket(ticketId) {
            const ticket = dashboardData.tickets.find(t => t.id === ticketId);
            if (!ticket) return;

            document.getElementById("ticket-title-id").textContent = ticket.id;
            document.getElementById("ticket-reply-id").value = ticket.id;
            document.getElementById("ticket-reply-message").value = "";

            try {
                const res = await fetch(`/admin/api/ticket-messages?ticket_id=${ticketId}`);
                if (res.ok) {
                    const messages = await res.json();
                    const area = document.getElementById("ticket-chat-area");
                    area.innerHTML = messages.map(msg => `
                        <div class="chat-message chat-message-${msg.sender_type}">
                            <div>${msg.content}</div>
                            <span class="chat-time">${formatDateTime(msg.created_at)}</span>
                        </div>
                    `).join("");
                    openModal("ticket-modal");
                    area.scrollTop = area.scrollHeight;
                }
            } catch (err) {
                showToast("Échec de récupération de la discussion", "error");
            }
        }

        async function replyToTicket(event) {
            event.preventDefault();
            const ticketId = document.getElementById("ticket-reply-id").value;
            const message = document.getElementById("ticket-reply-message").value;

            const params = new URLSearchParams();
            params.append("action", "reply_ticket");
            params.append("ticket_id", ticketId);
            params.append("message", message);

            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: params
                });
                if (res.ok) {
                    showToast("Réponse transmise");
                    closeModal("ticket-modal");
                    await refreshDashboardData();
                }
            } catch (err) {
                showToast("Erreur réseau", "error");
            }
        }

        async function closeTicket(ticketId) {
            if (!confirm("Marquer ce ticket comme résolu et le fermer ?")) return;
            const params = new URLSearchParams();
            params.append("action", "close_ticket");
            params.append("ticket_id", ticketId);

            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: params
                });
                if (res.ok) {
                    showToast("Ticket fermé");
                    await refreshDashboardData();
                }
            } catch (err) {
                showToast("Erreur réseau", "error");
            }
        }

        async function saveSettings(event) {
            event.preventDefault();
            const form = event.target;
            const formData = new FormData(form);
            const params = new URLSearchParams();
            params.append("action", "save_settings");
            for (const pair of formData.entries()) {
                params.append(pair[0], pair[1]);
            }

            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: params
                });
                if (res.ok) {
                    showToast("Configuration enregistrée avec succès");
                    await refreshDashboardData();
                }
            } catch (err) {
                showToast("Erreur réseau lors de l'enregistrement", "error");
            }
        }

        // Recherche et filtres serveur avec temporisation pour éviter une requête par frappe.
        function filterOrders() {
            clearTimeout(orderFilterTimer);
            ordersPagination.page = 1;
            orderFilterTimer = setTimeout(refreshDashboardData, 250);
        }

        let bulkWalletOperationId = "";

        async function bulkCreditWallets(event) {
            event.preventDefault();
            const form = event.target;
            const amount = Number(document.getElementById("bulk-wallet-amount").value);
            const confirmation = document.getElementById("bulk-wallet-confirmation").value.trim();
            if (!Number.isFinite(amount) || amount < 0.01 || amount > 10000) {
                showToast("Montant invalide (0,01 $ à 10 000 $)", "error");
                return;
            }
            if (confirmation !== "CREDIT ALL") {
                showToast("Saisissez exactement CREDIT ALL", "error");
                return;
            }
            if (!window.confirm(`Ajouter ${amount.toFixed(2)} $ au solde de TOUS les utilisateurs ?`)) {
                return;
            }

            if (!bulkWalletOperationId) {
                const randomPart = window.crypto && window.crypto.randomUUID
                    ? window.crypto.randomUUID().replaceAll("-", "_")
                    : `${Date.now()}_${Math.random().toString(36).slice(2)}`;
                bulkWalletOperationId = `bulk_${randomPart}`;
            }
            const params = new URLSearchParams({
                action: "bulk_credit_wallets",
                amount: amount.toFixed(2),
                confirmation,
                operation_id: bulkWalletOperationId,
            });
            const button = document.getElementById("bulk-wallet-credit-button");
            button.disabled = true;
            button.textContent = "Crédit en cours...";
            try {
                const res = await fetch("/admin", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded",
                        "X-Dashboard-Write-Token": dashboardWriteToken,
                    },
                    body: params,
                });
                const payload = await res.json();
                if (!res.ok || !payload.ok) {
                    throw new Error(payload.error || "Le crédit global a échoué");
                }
                showToast(`${payload.credited_count} utilisateur(s) crédité(s) de ${amount.toFixed(2)} $`);
                bulkWalletOperationId = "";
                form.reset();
                await refreshDashboardData();
            } catch (err) {
                showToast(err.message || "Erreur réseau", "error");
            } finally {
                button.disabled = false;
                button.textContent = "Ajouter à tous";
            }
        }

        function filterCustomers() {
            const query = document.getElementById("customer-search").value.toLowerCase();
            const rows = document.querySelectorAll("#customers-table tbody tr");

            rows.forEach(row => {
                if (row.cells.length < 3) return;
                const text = row.innerText.toLowerCase();
                row.style.display = text.includes(query) ? "" : "none";
            });
        }

        function filterTickets() {
            const status = document.getElementById("ticket-filter-status").value;
            const rows = document.querySelectorAll("#tickets-table tbody tr");

            rows.forEach(row => {
                if (row.cells.length < 5) return;
                const badge = row.querySelector(".badge").textContent;
                row.style.display = (!status || badge === status) ? "" : "none";
            });
        }

        // ═══ PREMIUM ENHANCEMENTS ═══

        // KPI counting animation
        function animateKpiValues() {
            document.querySelectorAll('.kpi-value').forEach(el => {
                const text = el.textContent.trim();
                const match = text.match(/^([\\d,.]+)/);
                if (!match) return;
                const raw = match[1].replace(/,/g, '');
                const target = parseFloat(raw);
                if (isNaN(target) || target === 0) return;
                const isDecimal = raw.includes('.');
                const suffix = text.slice(match[0].length);
                el.classList.add('counting');
                const duration = 900;
                const start = performance.now();
                function tick(now) {
                    const elapsed = now - start;
                    const progress = Math.min(elapsed / duration, 1);
                    const eased = 1 - Math.pow(1 - progress, 3);
                    const current = target * eased;
                    el.textContent = (isDecimal ? current.toFixed(2) : Math.round(current)) + suffix;
                    if (progress < 1) requestAnimationFrame(tick);
                    else el.classList.remove('counting');
                }
                requestAnimationFrame(tick);
            });
        }

        // Progress bar control
        function showProgress() {
            const bar = document.getElementById('global-progress');
            const fill = document.getElementById('global-progress-bar');
            if (!bar || !fill) return;
            bar.classList.add('active');
            fill.style.width = '0%';
            setTimeout(() => fill.style.width = '35%', 50);
            setTimeout(() => fill.style.width = '65%', 300);
            setTimeout(() => fill.style.width = '85%', 800);
        }

        function hideProgress() {
            const bar = document.getElementById('global-progress');
            const fill = document.getElementById('global-progress-bar');
            if (!bar || !fill) return;
            fill.style.width = '100%';
            setTimeout(() => {
                bar.classList.remove('active');
                fill.style.width = '0%';
            }, 300);
        }

        // Skeleton loading for KPIs
        function showKpiSkeleton() {
            const container = document.getElementById('kpi-container');
            if (!container) return;
            container.innerHTML = `<div class="kpi-grid">${
                [1,2,3,4].map(() => `<div class="skeleton-kpi skeleton">
                    <div class="skeleton-line w60 skeleton"></div>
                    <div class="skeleton-line lg skeleton"></div>
                    <div class="skeleton-line w80 skeleton"></div>
                </div>`).join('')
            }</div>`;
        }

        // Real-time clock
        function updateClock() {
            const el = document.getElementById('clock-time');
            if (el) el.textContent = new Date().toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
        }
        setInterval(updateClock, 1000);
        updateClock();

        // Scroll-to-top
        const scrollBtn = document.getElementById('scroll-to-top');
        if (scrollBtn) {
            const mainEl = document.querySelector('main');
            (mainEl || window).addEventListener('scroll', () => {
                const scrollY = mainEl ? mainEl.scrollTop : window.scrollY;
                scrollBtn.classList.toggle('visible', scrollY > 400);
            }, {passive: true});
            scrollBtn.addEventListener('click', () => {
                (mainEl || window).scrollTo({top: 0, behavior: 'smooth'});
            });
        }

        // Escape key to close modals
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal.active').forEach(m => {
                    m.classList.remove('active');
                });
            }
        });

        // Keyboard shortcuts: Ctrl+1 to Ctrl+9 for tab navigation
        document.addEventListener('keydown', e => {
            if (!e.ctrlKey || e.shiftKey || e.altKey || e.metaKey) return;
            const num = parseInt(e.key);
            if (num >= 1 && num <= 9) {
                const tabs = document.querySelectorAll('nav a[data-tab]');
                if (tabs[num - 1]) {
                    e.preventDefault();
                    tabs[num - 1].click();
                }
            }
        });

        // Button ripple effect
        document.addEventListener('click', e => {
            const btn = e.target.closest('.btn');
            if (!btn) return;
            const rect = btn.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const ripple = document.createElement('span');
            ripple.className = 'ripple-circle';
            ripple.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX - rect.left - size/2}px;top:${e.clientY - rect.top - size/2}px`;
            btn.appendChild(ripple);
            ripple.addEventListener('animationend', () => ripple.remove());
        });

        // Hook into existing refreshDashboardData to show progress
        const _originalRefreshDashboardData = typeof refreshDashboardData === 'function' ? refreshDashboardData : null;
        if (_originalRefreshDashboardData) {
            // We patch the refreshUI function to trigger KPI animation
            const _origRefreshUI = refreshUI;
            refreshUI = function() {
                _origRefreshUI();
                setTimeout(animateKpiValues, 50);
            };
        }

        // Run initial animations after first render
        setTimeout(animateKpiValues, 600);

    </script>
</body>
</html>
"""

    # Remplacements de chaînes simples pour éviter les syntax errors f-string
    page = (
        html_template.replace("__SHOP_NAME__", html.escape(shop_name))
        .replace("__ALERTS_HTML__", alerts_html)
        .replace("__KPIS_HTML__", kpis_html)
        .replace("__JSON_DATA__", json_data_str)
        .replace("__DASHBOARD_WRITE_TOKEN__", json.dumps(dashboard_write_token))
    )
    for tab in allowed_tabs:
        page = page.replace(f"__ACTIVE_{tab.upper()}__", "active" if tab == active_tab else "")
        page = page.replace(f"__PANEL_{tab.upper()}__", "active" if tab == active_tab else "")
    return page
