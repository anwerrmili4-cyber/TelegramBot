"""OpenAPI document and Swagger UI for the public buyer API."""

from __future__ import annotations

import html
import json

from config import public_base_url_from_environment


def openapi_document() -> dict:
    base_url = public_base_url_from_environment()
    error_schema = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "example": False},
            "code": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["success", "code", "message"],
    }
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "BlackMarket Buyer API",
            "version": "1.1.0",
            "description": (
                "Wallet-funded reseller API. Telegram users can create their own key "
                "from the bot's Reseller API dashboard. "
                "Purchases require a unique Idempotency-Key and use the wallet attached "
                "to the key's Telegram user. Send the API key on every protected request "
                "as Authorization: Bearer <API_KEY>; never place it in a URL or JSON body."
            ),
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/api/v2/telegram-buyer/products": {
                "get": {
                    "summary": "List products available to the buyer key",
                    "security": [{"BuyerKeyAuth": []}],
                    "responses": {
                        "200": {
                            "description": "Available product catalogue",
                            "content": {"application/json": {"schema": {
                                "$ref": "#/components/schemas/ProductsResponse"
                            }}},
                        },
                        "401": {"$ref": "#/components/responses/Unauthorized"},
                        "429": {"$ref": "#/components/responses/RateLimited"},
                    },
                },
            },
            "/api/v2/telegram-buyer/balance": {
                "get": {
                    "summary": "Get the wallet balance attached to the buyer key",
                    "security": [{"BuyerKeyAuth": []}],
                    "responses": {
                        "200": {
                            "description": "Current wallet balance",
                            "content": {"application/json": {"schema": {
                                "$ref": "#/components/schemas/BalanceResponse"
                            }}},
                        },
                        "401": {"$ref": "#/components/responses/Unauthorized"},
                        "429": {"$ref": "#/components/responses/RateLimited"},
                    },
                },
            },
            "/api/v2/telegram-buyer/purchase": {
                "post": {
                    "summary": "Purchase a product using wallet balance",
                    "security": [{"BuyerKeyAuth": []}],
                    "parameters": [{
                        "name": "Idempotency-Key",
                        "in": "header",
                        "required": True,
                        "schema": {"type": "string", "minLength": 8, "maxLength": 128},
                        "description": "Reuse only when retrying the exact same purchase.",
                    }],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "$ref": "#/components/schemas/PurchaseRequest"
                        }}},
                    },
                    "responses": {
                        "200": {
                            "description": "Purchase completed and delivered",
                            "content": {"application/json": {"schema": {
                                "$ref": "#/components/schemas/PurchaseResponse"
                            }}},
                        },
                        "202": {
                            "description": "Payment completed; delivery is processing",
                            "content": {"application/json": {"schema": {
                                "$ref": "#/components/schemas/PurchaseResponse"
                            }}},
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        "401": {"$ref": "#/components/responses/Unauthorized"},
                        "404": {"$ref": "#/components/responses/NotFound"},
                        "409": {"$ref": "#/components/responses/Conflict"},
                        "429": {"$ref": "#/components/responses/RateLimited"},
                    },
                },
            },
            "/api/v2/telegram-buyer/orders/{orderCode}": {
                "get": {
                    "summary": "Get purchase status and completed delivery",
                    "security": [{"BuyerKeyAuth": []}],
                    "description": (
                        "Use this endpoint when POST /purchase returns HTTP 202 with "
                        "status=processing. Poll no more often than every 5 seconds. "
                        "Stop when terminal=true. The API key can access only orders "
                        "created with that same key."
                    ),
                    "parameters": [
                        {"$ref": "#/components/parameters/OrderCode"},
                    ],
                    "responses": {
                        "200": {
                            "description": (
                                "Current order state. A processing response includes a "
                                "Retry-After: 5 header; deliveredAccounts is populated "
                                "when status becomes delivered."
                            ),
                            "content": {"application/json": {"schema": {
                                "$ref": "#/components/schemas/PurchaseResponse"
                            }}},
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        "401": {"$ref": "#/components/responses/Unauthorized"},
                        "404": {"$ref": "#/components/responses/NotFound"},
                        "429": {"$ref": "#/components/responses/RateLimited"},
                    },
                },
            },
        },
        "components": {
            "securitySchemes": {
                "BuyerKeyAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "Buyer API key",
                    "description": "API key issued by the Telegram Reseller API dashboard.",
                },
            },
            "parameters": {
                "OrderCode": {
                    "name": "orderCode",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "pattern": "^BM-[1-9][0-9]*$"},
                    "example": "BM-123",
                },
            },
            "schemas": {
                "Product": {
                    "type": "object",
                    "properties": {
                        "_id": {"type": "string", "example": "12"},
                        "product_name": {"type": "string", "example": "Premium Account"},
                        "description": {"type": "string"},
                        "walletCurrency": {"type": "string", "example": "USDT"},
                        "walletPricing": {"type": "number", "format": "double"},
                        "manualDelivery": {"type": "boolean"},
                        "stats": {
                            "type": "object",
                            "properties": {
                                "available": {"type": "integer", "description": "-1 means unlimited"},
                                "sold": {"type": "integer"},
                            },
                        },
                    },
                },
                "ProductsResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": True},
                        "walletCurrency": {"type": "string", "example": "USDT"},
                        "products": {"type": "array", "items": {"$ref": "#/components/schemas/Product"}},
                    },
                },
                "BalanceResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": True},
                        "walletCurrency": {"type": "string", "example": "USDT"},
                        "balance": {"type": "number", "format": "double", "example": 25.5},
                        "balanceText": {"type": "string", "example": "25.50 USDT"},
                        "updatedAt": {"type": "string", "format": "date-time"},
                    },
                },
                "PurchaseRequest": {
                    "type": "object",
                    "required": ["product_id", "quantity"],
                    "properties": {
                        "product_id": {"type": "string", "example": "12"},
                        "quantity": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                },
                "PurchaseResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": True},
                        "orderCode": {"type": "string", "example": "BM-123"},
                        "productType": {"type": "string"},
                        "quantity": {"type": "integer"},
                        "amount": {"type": "number", "format": "double"},
                        "balance": {"type": "number", "format": "double"},
                        "status": {
                            "type": "string",
                            "enum": ["delivered", "processing", "cancelled", "refunded"],
                        },
                        "terminal": {
                            "type": "boolean",
                            "description": "Stop polling when true.",
                        },
                        "deliveredAccounts": {"type": "array", "items": {"type": "string"}},
                        "updatedAt": {"type": "string", "format": "date-time"},
                        "deliveredAt": {"type": "string", "format": "date-time"},
                    },
                },
                "Error": error_schema,
            },
            "responses": {
                "BadRequest": _error_response("Invalid request", error_schema),
                "Unauthorized": _error_response("Invalid API key", error_schema),
                "NotFound": _error_response("Product not found", error_schema),
                "Conflict": _error_response("Stock or idempotency conflict", error_schema),
                "RateLimited": {
                    **_error_response("Rate limit exceeded", error_schema),
                    "headers": {
                        "Retry-After": {
                            "description": "Seconds before another request may be attempted.",
                            "schema": {"type": "integer"},
                        },
                    },
                },
            },
        },
    }


def _error_response(description: str, schema: dict) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }


def swagger_html() -> str:
    spec = json.dumps(openapi_document(), ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(openapi_document()["info"]["title"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
  <style>body{{margin:0;background:#f7f8fa}} .topbar{{display:none}}</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>SwaggerUIBundle({{spec:{spec},dom_id:'#swagger-ui',deepLinking:true}});</script>
</body>
</html>"""
