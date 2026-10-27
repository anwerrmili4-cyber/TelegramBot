# Refactor Task List

## Task 0: Adopt the target architecture

**Description:** Record the architecture that guides every extraction so new
modules do not recreate the same coupling under different filenames.

**Acceptance criteria:**
- [x] The chosen architecture defines responsibilities and dependency direction.
- [x] Strict MVC, microservices, and a big-bang rewrite are evaluated explicitly.
- [x] Module-responsibility and compatibility-facade rules are documented.

**Verification:**
- [x] ADR accepted at `docs/decisions/0001-modular-layered-monolith.md`.
- [x] `tasks/plan.md` uses the same layer names and migration order.

**Dependencies:** None

**Files touched:**
- `docs/decisions/0001-modular-layered-monolith.md`
- `tasks/plan.md`
- `tasks/todo.md`

**Estimated scope:** Small (3 files)

## Task 1: Establish fast, reproducible test commands

**Description:** Record the current full-suite result and provide documented commands for bot, webhook, repository, and admin UI changes so normal edits avoid an unnecessary full-suite run.

**Acceptance criteria:**
- [x] The current full-suite failures are recorded by test name and category.
- [x] Focused commands cover bot presentation, webhook catalog actions, repositories, and admin UI.
- [x] The commands use existing pytest and Node test tooling without adding a new dependency.

**Verification:**
- [x] Each focused command discovers and runs at least one intended test.
- [x] `python -m pytest --collect-only -q` succeeds (1,008 tests collected).
- [x] `npm test` succeeds in `admin-ui` or matches the recorded baseline.

**Dependencies:** None

**Files likely touched:**
- `tasks/plan.md`
- `tasks/todo.md`
- `README.md` or a small test-command script

**Estimated scope:** Small (1-3 files)

## Task 2: Stabilize refactor-blocking baseline failures

**Description:** Repair only failures that affect payment result handling, catalog/stock behavior, or modules selected for extraction. Unrelated failures remain documented rather than bundled into the refactor.

**Acceptance criteria:**
- [x] The undefined `error_code` payment crash is covered by a regression test and fixed.
- [x] Selected bot and catalog tests have a stable, repeatable baseline.
- [x] No unrelated feature cleanup is included.

**Verification:**
- [x] `python -m pytest tests/test_bot_design.py -q` (167 passed).
- [x] `python -m pytest tests/test_reseller_service.py tests/test_stock_alert_service.py -q` (70 passed).
- [x] Full-suite result is compared with the recorded baseline (1,009 passed).

**Dependencies:** Task 1

**Files likely touched:**
- `bot.py`
- `tests/test_bot_design.py`
- Selected reseller or stock files only if confirmed blockers

**Estimated scope:** Medium (2-5 files)

## Task 3: Extract bot presentation helpers

**Description:** Move rich text, method formatting, offer-card rendering, duration parsing, and admin previews into separate leaf modules organized by responsibility. Keep imports or forwarding wrappers in `bot.py` for existing callers and monkeypatches.

**Acceptance criteria:**
- [x] Rendered text is byte-for-byte equivalent for representative English, French, and Arabic fixtures.
- [x] Existing imports from `bot` continue to work.
- [x] The new module has no Telegram network, database write, or application startup side effects.

**Verification:**
- [x] `python -m pytest tests/test_bot_design.py -k "compact_offer or rich_text or preview" -q`
- [x] `python -m pytest tests/test_i18n.py tests/test_warranty_service.py -q`
- [x] `python -m ruff check app/bot/presentation.py app/bot/methods_presentation.py app/bot/offer_cards.py app/bot/text_previews.py bot.py`

**Dependencies:** Tasks 1-2

**Files likely touched:**
- `app/bot/presentation.py`
- `app/bot/methods_presentation.py`
- `app/bot/offer_cards.py`
- `app/bot/text_previews.py`
- `app/bot/__init__.py`
- `bot.py`
- `tests/test_bot_design.py`

**Estimated scope:** Medium (4 files)

**Incremental progress:**
- [x] Extract rich-text and Premium emoji helpers into `app/bot/presentation.py`.
- [x] Preserve the existing helper imports from `bot.py`.
- [x] Add a compatibility test for the facade and extracted module.
- [x] Extract method formatting, offer cards, duration parsing, and admin previews as independent slices.

## Task 4: Extract bot announcements and broadcasts

**Description:** Move stock, flash-sale, supplier-change, and queued broadcast behavior behind an announcement service while leaving handler registration in `bot.py`.

**Acceptance criteria:**
- [x] Announcement text, recipient selection, and deduplication remain unchanged.
- [x] Background job entry points retain their current names and signatures.
- [x] External send operations remain mockable at the same boundaries.

**Verification:**
- [x] `python -m pytest tests/test_bot_design.py -k "announcement or broadcast or flash_sale or restock" -q`
- [x] `python -m pytest tests/test_notification_service.py tests/test_inactive_offer_announcements.py -q`
- [x] Importing `app.bot.announcements` performs no sends or database mutations.

**Dependencies:** Task 3

**Files likely touched:**
- `app/bot/announcements.py`
- `bot.py`
- `tests/test_bot_design.py`
- `tests/test_inactive_offer_announcements.py`

**Estimated scope:** Medium (4 files)

## Task 5: Extract catalog and offer navigation handlers

**Description:** Move the catalog browsing callback slice into a handler module using explicit dependencies for database access, keyboards, and rendering.

**Acceptance criteria:**
- [x] Existing callback data remains compatible.
- [x] Single-offer and multi-offer navigation produce the same messages and keyboards.
- [x] Handler registration and startup remain in `bot.py` until a later plan.

**Verification:**
- [x] `python -m pytest tests/test_keyboards.py tests/test_bot_design.py -k "catalog or offer or service" -q`
- [x] `python -m pytest tests/test_startup.py tests/test_bot_runtime_features.py -q`

**Dependencies:** Task 3

**Files likely touched:**
- `app/bot/handlers/catalog.py`
- `app/bot/handlers/__init__.py`
- `bot.py`
- `tests/test_bot_design.py`

**Estimated scope:** Medium (4 files)

## Checkpoint: Bot boundary

- [x] Tasks 1-5 acceptance criteria pass.
- [x] `bot.py` remains a working compatibility facade.
- [x] Full suite is no worse than baseline (1,087 passed; one transient Windows loopback failure passed alone).
- [x] Review before starting webhook extraction.

## Task 6: Extract admin catalog form parsing and actions

**Description:** Move duration parsing, validation, and add/update catalog action logic from `api/webhook.py` into a focused application module with explicit inputs and return values.

**Acceptance criteria:**
- [ ] Add and update behavior, including optional duration/warranty fields, is unchanged.
- [ ] Validation errors preserve their existing status and message.
- [ ] The action module does not depend on `BaseHTTPRequestHandler`.

**Verification:**
- [ ] `python -m pytest tests/test_webhook_http.py -k "catalog or offer" -q`
- [ ] `python -m pytest tests/test_optional_bot_terms.py tests/test_warranty_service.py -q`

**Dependencies:** Checkpoint: Bot boundary

**Files likely touched:**
- `app/web/catalog_actions.py`
- `api/webhook.py`
- `tests/test_webhook_http.py`
- `tests/test_optional_bot_terms.py`

**Estimated scope:** Medium (4 files)

## Task 7: Introduce a thin webhook catalog dispatcher

**Description:** Delegate catalog POST actions and related GET payloads from the legacy handler to focused route/controller functions while preserving authentication and response serialization.

**Acceptance criteria:**
- [ ] The legacy handler contains routing and response adaptation, not catalog business logic.
- [ ] Authentication and CSRF/write-token checks remain at the HTTP boundary.
- [ ] Status codes and JSON payloads match existing HTTP tests.

**Verification:**
- [ ] `python -m pytest tests/test_webhook_http.py tests/test_dashboard_api.py -k "catalog or auth" -q`
- [ ] `python -m pytest tests/test_web_apps.py -q`

**Dependencies:** Task 6

**Files likely touched:**
- `app/web/routes/admin_catalog.py`
- `app/web/routes/__init__.py`
- `api/webhook.py`
- `tests/test_webhook_http.py`

**Estimated scope:** Medium (4 files)

## Checkpoint: HTTP boundary

- [ ] Tasks 6-7 acceptance criteria pass.
- [ ] Admin UI build succeeds.
- [ ] Full suite is no worse than baseline.
- [ ] Review before persistence extraction.

## Task 8: Define catalog repository contracts

**Description:** Add contract tests for catalog reads, writes, visibility, ordering, stock, and compatibility return values before moving implementation out of `database.py`.

**Acceptance criteria:**
- [ ] Contract tests cover add, update, archive, reorder, visibility, and optional term flags.
- [ ] Public return shapes used by bot and admin are explicit.
- [ ] No implementation is moved in this task.

**Verification:**
- [ ] `python -m pytest tests/test_repositories.py tests/test_catalog_performance.py -q`
- [ ] New contract tests fail if compatibility fields are removed.

**Dependencies:** Task 1

**Files likely touched:**
- `tests/test_repositories.py`
- `tests/test_catalog_performance.py`

**Estimated scope:** Small (2 files)

## Task 9: Move catalog persistence behind a repository

**Description:** Move catalog CRUD and query implementations into `app/repositories/catalog.py`; retain forwarding functions in `database.py` so callers migrate independently.

**Acceptance criteria:**
- [ ] Existing `database.add_offer`, `update_offer`, and catalog query imports still work.
- [ ] Stored documents and sorting remain unchanged.
- [ ] Cache invalidation and stock notifications still occur exactly once.

**Verification:**
- [ ] `python -m pytest tests/test_repositories.py tests/test_catalog_performance.py tests/test_offer_stock_control.py -q`
- [ ] `python -m pytest tests/test_webhook_http.py -k "catalog or offer" -q`

**Dependencies:** Task 8

**Files likely touched:**
- `app/repositories/catalog.py`
- `app/repositories/__init__.py`
- `database.py`
- `tests/test_repositories.py`

**Estimated scope:** Medium (4 files)

## Task 10: Move order persistence behind a repository

**Description:** Move order creation, retrieval, status updates, and listing queries into `app/repositories/orders.py` while retaining `database.py` wrappers.

**Acceptance criteria:**
- [ ] Order snapshots, totals, warranty fields, and statuses remain unchanged.
- [ ] Existing callers continue to import from `database`.
- [ ] Payment reference and inventory transactions retain current atomicity.

**Verification:**
- [ ] `python -m pytest tests/test_order_service.py tests/test_payment_service.py tests/test_repositories.py -q`
- [ ] `python -m pytest tests/test_manual_payment_service.py tests/test_payment_reference_claims.py -q`

**Dependencies:** Task 9

**Files likely touched:**
- `app/repositories/orders.py`
- `app/repositories/__init__.py`
- `database.py`
- `tests/test_repositories.py`

**Estimated scope:** Medium (4 files)

## Checkpoint: Persistence boundary

- [ ] Tasks 8-10 acceptance criteria pass.
- [ ] Existing database imports remain compatible.
- [ ] Full suite is no worse than baseline.
- [ ] Review before deleting compatibility code.

## Task 11: Remove proven dead duplication

**Description:** Remove only helpers proven unused after the extractions; keep compatibility wrappers that still have callers.

**Acceptance criteria:**
- [ ] Every deletion has no references under `rg` and is covered by surviving behavior tests.
- [ ] No public import is removed without a migration task.
- [ ] No unrelated formatting or renaming is included.

**Verification:**
- [ ] Focused suites for all affected modules pass.
- [ ] `python -m compileall -q app api bot.py database.py`
- [ ] `python -m ruff check` reports no new violations.

**Dependencies:** Checkpoint: Persistence boundary

**Files likely touched:**
- `bot.py`
- `api/webhook.py`
- `database.py`

**Estimated scope:** Medium (3 files)

## Task 12: Final regression and documentation

**Description:** Run checkpoint-level verification, document module ownership and test commands, and compare results with the original baseline.

**Acceptance criteria:**
- [ ] Full suite has no regressions from the recorded baseline.
- [ ] Admin tests and production build pass.
- [ ] Module boundaries and focused commands are documented.

**Verification:**
- [ ] `python -m pytest -q`
- [ ] `npm test` in `admin-ui`
- [ ] `npm run build` in `admin-ui`
- [ ] Deployment configuration tests pass.

**Dependencies:** Task 11

**Files likely touched:**
- `README.md`
- `tasks/plan.md`
- `tasks/todo.md`

**Estimated scope:** Small (3 files)

## Checkpoint: Complete

- [ ] All task acceptance criteria are satisfied.
- [ ] Full regression results are recorded.
- [ ] Changes are ready for review in small, ordered commits.
