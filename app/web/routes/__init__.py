"""Native FastAPI route handlers, one module per feature.

Handlers parse the request, call one service and format the response.
Anything not routed here still goes through :mod:`app.web.legacy_bridge`.
"""
