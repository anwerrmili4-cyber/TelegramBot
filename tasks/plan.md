# Implementation Plan: Modular Layered Architecture Migration

## Overview

Migrate the existing layered monolith into explicit controller, presentation,
domain-service, repository, and infrastructure boundaries. The immediate goal
is to remove mixed responsibilities from `bot.py`, `api/webhook.py`, and
`database.py` through small behavior-preserving extractions. Each phase keeps
current public imports working, adds focused tests, and ends at a deployable
checkpoint. `api/dashboard.py` is deliberately excluded from this first plan
because the React admin already replaced most of that legacy surface.

## Architecture Decisions

- Adopt the modular layered monolith defined in
  `docs/decisions/0001-modular-layered-monolith.md`; do not introduce a strict
  MVC tree or microservices.
- Keep `bot.py`, `api/webhook.py`, and `database.py` as temporary compatibility facades. Existing imports continue to work while implementation moves into focused modules.
- Extract one vertical behavior group at a time; do not reorganize unrelated features in the same change.
- Move pure formatting and validation before stateful handlers, HTTP routing, or persistence code.
- Reuse the existing `app/bot`, `app/web/routes`, and `app/repositories` package structure instead of creating a competing architecture.
- Keep controllers transport-specific and thin; business decisions belong in
  `app/domain`, persistence in `app/repositories`, and external calls in focused
  adapters.
- Create modules around cohesive capabilities, not arbitrary line ranges.
  Split a module further whenever it owns independent behavior, dependencies,
  or side effects.
- Characterize current behavior with focused tests before moving code. A move is complete only when old and new import paths behave identically.
- Do not use the full test suite for every edit. Run focused tests per task and the full suite only at checkpoints.

## Target Dependency Rule

```text
entry points -> controllers/routes -> domain services -> repositories -> MongoDB
                         |                  |
                         v                  v
                   presentation     infrastructure adapters
```

Dependencies must not point back toward entry points or controllers. Temporary
facade imports are allowed only while a named migration task is incomplete.

## Dependency Order

```text
Baseline and focused test commands
        |
        +--> Pure bot presentation extraction
        |          |
        |          +--> Bot announcements and customer handlers
        |
        +--> Webhook request/action boundaries
        |          |
        |          +--> Admin catalog action routes
        |
        +--> Repository contracts
                   |
                   +--> Catalog and order persistence extraction
```

## Task List

### Phase 1: Safety and Fast Feedback

- [x] Task 1: Record the failing-test baseline and add focused test commands.
- [x] Task 2: Fix or quarantine only confirmed baseline failures that block refactoring.

### Checkpoint: Stable Baseline

- [x] Focused bot, webhook, repository, and admin UI commands pass.
- [x] The serial full suite passes with no remaining baseline failures.
- [x] No unrelated production behavior has changed.

### Phase 2: Decompose `bot.py`

- [x] Task 3: Extract pure bot presentation into focused rich-text, method-card, offer-card, and admin-preview modules.
- [x] Task 4: Extract stock, sale, and broadcast announcement logic into `app/bot/announcements.py`.
- [x] Task 5: Extract one customer handler slice (catalog and offer navigation) into `app/bot/handlers/catalog.py`.

### Checkpoint: Bot Boundary

- [x] `bot.py` still exposes all names used by tests and startup wiring.
- [x] Focused bot tests and runtime startup tests pass.
- [x] Telegram callback data and rendered customer text remain unchanged.

### Phase 3: Decompose `api/webhook.py`

- [ ] Task 6: Extract duration/form validation and admin catalog mutations into a catalog action module.
- [ ] Task 7: Replace the catalog action branch with a thin dispatcher while preserving HTTP responses.

### Checkpoint: HTTP Boundary

- [ ] Catalog create/edit/archive/reorder HTTP tests pass.
- [ ] Authentication, status codes, and response payloads remain unchanged.
- [ ] The legacy handler delegates instead of duplicating business rules.

### Phase 4: Decompose `database.py`

- [ ] Task 8: Define and test catalog repository contracts behind existing `database.py` functions.
- [ ] Task 9: Move catalog persistence into `app/repositories/catalog.py` with compatibility wrappers.
- [ ] Task 10: Move order persistence into `app/repositories/orders.py` with compatibility wrappers.

### Checkpoint: Persistence Boundary

- [ ] Existing callers can still import from `database` without modification.
- [ ] Repository, catalog, order, warranty, and payment tests pass.
- [ ] MongoDB queries and indexes are unchanged unless separately approved.

### Phase 5: Cleanup

- [ ] Task 11: Remove dead duplicate helpers only after import and coverage checks prove they are unused.
- [ ] Task 12: Run the full regression suite, admin tests, build, and deployment configuration checks.

### Checkpoint: Complete

- [ ] All planned extractions are behavior-preserving.
- [ ] Full-suite failures are no worse than the recorded baseline.
- [ ] No compatibility facade contains new business logic.
- [ ] Module ownership and focused test commands are documented.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Circular imports between `bot.py` and extracted handlers | High | Pass dependencies explicitly and keep shared constants/types in leaf modules. |
| Tests monkeypatch names on `bot` or `database` | High | Preserve facade names and add compatibility tests before moving implementations. |
| Hidden side effects during module import | High | Characterize startup/import behavior and move registration only after pure helpers. |
| HTTP response drift | High | Assert status, payload, and authentication behavior at the HTTP boundary. |
| Database query or serialization drift | High | Compare stored documents and public return values in repository contract tests. |
| Dirty working tree mixes unrelated changes | Medium | Use narrow diffs and one logical commit per task; never bulk-format touched modules. |
| Full suite is slow and currently has failures | Medium | Use focused commands per task and compare checkpoint results with the saved baseline. |

## Explicitly Out of Scope

- Rewriting the bot framework or changing callback identifiers.
- Changing database schemas, indexes, or stored document formats.
- Redesigning the admin UI.
- Splitting `api/dashboard.py` before the three higher-value boundaries are stable.
- Implementing optional improvements discovered during extraction without separate approval.

## Open Questions for Review

- Should each numbered task be its own commit once the existing dirty working
  tree has been separated safely?
- After Phase 4, should the legacy `api/dashboard.py` renderer be deprecated or receive a separate decomposition plan?
