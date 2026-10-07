"""MongoDB queries, one module per collection group.

Collections move here from ``database.py`` one group at a time; ``database``
re-exports them so existing callers keep working until they import from here.
"""
