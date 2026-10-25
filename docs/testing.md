# Test Commands and Refactor Baseline

Use the smallest command that covers the code being changed. Run the complete
suite only at a phase checkpoint or before release.

## Focused commands

### Bot presentation

```powershell
python -m pytest tests/test_bot_design.py -k "compact_offer or rich_text or preview" -q
```

### Webhook catalog actions

```powershell
python -m pytest tests/test_webhook_http.py -k "catalog or offer" -q
```

### Repository contracts and catalog performance

```powershell
python -m pytest tests/test_repositories.py tests/test_catalog_performance.py -q
```

### Admin UI

```powershell
Push-Location admin-ui
npm test
Pop-Location
```

### Test collection

```powershell
python -m pytest --collect-only -q
```

### Complete Python suite

```powershell
python -m pytest -q
```

## Baseline recorded on 2026-10-20

The complete Python suite collected 1,008 tests and finished in 182.60 seconds:

- 1,004 passed.
- 4 failed.
- 2,267 warnings were reported.

Known baseline failures:

| Test | Category | Refactor impact |
| --- | --- | --- |
| `tests/test_bot_design.py::test_out_of_stock_supplier_discount_uses_bot_flash_sale_design` | Bot flash-sale announcement | Blocks the later announcement extraction, not pure presentation work. |
| `tests/test_reseller_service.py::test_restock_detection_baselines_then_reports_only_increases` | Supplier restock detection | Blocks the later announcement extraction. |
| `tests/test_reseller_service.py::test_purchase_is_refused_when_the_supplier_just_ran_out` | Supplier stock validation | Does not block pure presentation extraction. |
| `tests/test_stock_alert_service.py::test_a_waiting_address_is_emailed_once_when_stock_returns` | Storefront stock alerts | Does not block pure presentation extraction. |

The payment-result `error_code` regression is not part of this baseline: its
focused payment and delivery tests pass.

## Stable checkpoint recorded on 2026-10-20

After repairing the four baseline failures and extracting the first bot
presentation slice, the complete serial suite finished in 102.90 seconds:

- 1,009 passed.
- 0 failed.
- 2,267 warnings were reported.

Run Python test commands serially on Windows. Concurrent pytest processes that
each open local webhook test servers caused transient connection-aborted errors;
the affected tests and the subsequent serial complete suite passed.
