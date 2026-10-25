# ADR-001: Adopt a modular layered monolith

## Status

Accepted

## Date

2026-10-20

## Context

The application serves several interfaces from one deployment: a Telegram bot,
an HTTP webhook and admin API, a React admin application, and a storefront. Its
largest Python entry points currently combine transport handling, presentation,
business rules, and persistence. Their problem is not a particular line count;
it is that unrelated capabilities share imports, state, and reasons to change.

The project already contains useful boundaries under `app/bot`, `app/domain`,
`app/repositories`, and `app/web`. Replacing those with a strict MVC tree would
create churn without solving the coupling between Telegram, HTTP, domain logic,
and MongoDB. Splitting the deployment into microservices would add network,
deployment, and transaction overhead that this application does not need.

The migration must preserve Telegram callback data, HTTP payloads, database
documents, error messages, and public imports while the old entry points are
still in use.

## Decision

Use a modular layered monolith with ports-and-adapters boundaries at external
systems.

### Module responsibilities

| Layer | Location | Responsibility |
| --- | --- | --- |
| Entry points | `bot.py`, `api/webhook.py`, Railway/Vercel startup files | Configuration, dependency wiring, handler registration, and compatibility exports only. |
| Controllers | `app/bot/handlers`, `app/web/routes` | Validate transport input, call one application service, and adapt the result to Telegram or HTTP. |
| Presentation | Focused modules under `app/bot`, keyboard/view modules, React applications | Format messages and UI output without writes or external sends. Split rich text, offer cards, method cards, previews, and other independent formats by responsibility. |
| Domain services | `app/domain` | Business rules for orders, payments, catalog, warranties, suppliers, and customers. |
| Repositories | `app/repositories` | MongoDB queries, atomic updates, serialization, and persistence contracts. |
| Infrastructure adapters | Focused provider, email, Telegram-file, and object-storage modules | Calls to third-party systems and parsing of their untrusted responses. |
| Shared core | `app/core`, `app/constants.py`, small feature-local contracts | Cross-cutting primitives that do not depend on controllers or presentation. |

### Dependency direction

```text
entry points
    |
    +--> controllers/routes --> domain services --> repositories --> MongoDB
    |             |                   |
    |             +--> presentation   +--> infrastructure adapters
    |
    +--> compatibility exports only
```

Lower layers must not import Telegram/HTTP controllers or application entry
points. Presentation code may read immutable formatting inputs but must not
write to MongoDB, send Telegram messages, or start background work. Controllers
must stay thin; reusable decisions belong in domain services.

### Decomposition rules

- Organize modules by business capability inside each layer (`catalog`,
  `orders`, `payments`, `support`) instead of creating one large generic module.
- Give each module one cohesive responsibility and one primary reason to
  change. Split it again whenever independent capabilities, dependencies, or
  side effects can be named.
- Keep handlers limited to transport concerns: validate input, call an
  application service, and adapt the result. Extract business decisions even
  when the handler itself is short.
- Keep `bot.py`, `api/webhook.py`, and `database.py` as compatibility facades
  until repository-wide searches and tests prove their callers have migrated.
- Move one behavior slice at a time and preserve its observable contract with
  focused tests before deleting the original implementation.
- Do not create empty layers or placeholder abstractions. A module is created
  only when a working behavior moves into it.

### Performance rules

The architecture itself does not make Python execution faster. Performance is
protected by keeping the application in one process and applying optimization
at the real boundaries:

- Batch database work in repositories and avoid per-row queries in controllers.
- Keep catalog/session caches close to their authoritative services and
  invalidate them from write paths.
- Keep supplier, email, and Telegram I/O out of rendering functions.
- Run independent external I/O concurrently only where ordering and provider
  rate limits permit it.
- Use focused test commands during migration and the full suite at checkpoints.

## Alternatives Considered

### Strict MVC

MVC maps cleanly to server-rendered web applications but poorly to a Telegram
bot plus JSON APIs and React clients. The domain and persistence layers would
still be needed, producing ambiguous "model" and "controller" modules.

### Feature-first packages containing every layer

This can work later, but moving every existing module immediately would create
a large import rewrite. The chosen layered locations preserve the structure the
project already uses while still naming modules by capability.

### Microservices

Rejected because they add network calls, distributed failure modes, deployment
coordination, and cross-service transaction problems without a demonstrated
scaling requirement.

### Big-bang rewrite

Rejected because payment, inventory, delivery, and supplier workflows contain
observable behavior that must remain compatible throughout the migration.

## Consequences

- Large entry points shrink gradually instead of through a risky rewrite.
- Telegram and HTTP controllers can share the same domain services.
- Database behavior becomes testable behind repository contracts.
- Focused tests become faster because pure presentation and service modules can
  be imported without application startup side effects.
- Compatibility facades temporarily add indirection and must not receive new
  business logic.
- Some existing `app/domain` modules still import `database.py`; repository
  migration will remove that dependency capability by capability.
