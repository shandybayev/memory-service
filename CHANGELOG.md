# Changelog

All notable changes to this memory service implementation.

## [0.1.0] - 2025-06-16 — Initial scaffold

### Added
- FastAPI monolith with full HTTP contract (`/health`, `/turns`, `/recall`, `/search`, user/session deletes).
- SQLAlchemy models for turns, memories, and search documents.
- Docker + compose with named volume `memory_data` at `/data`.
- Pytest stubs for contract, isolation, malformed input, and persistence.

### Observed
- Contract-first approach made it easy to validate shapes before extraction/retrieval logic landed.
- SQLite WAL on a mounted volume was sufficient for restart persistence without Postgres ops overhead.

---

## [0.2.0] - 2025-06-16 — Persistence + turn ingestion

### Changed
- Wired `POST /turns` to persist messages (including tool role), metadata, and timestamps.
- Added payload size guard (`MAX_TURN_PAYLOAD_BYTES`) and validation error handling.

### Observed
- Anonymous turns (`user_id: null`) store successfully but skip extraction — documented as intentional.
- Multi-message turns with tool calls index each snippet separately for retrieval.

---

## [0.3.0] - 2025-06-16 — Rule-based extraction

### Added
- Deterministic extractor for employment, location, preferences, opinions, pets/family, and move events.
- Normalized memory keys (`employment.company`, `location.residence`, etc.).
- Optional OpenAI extraction path with automatic fallback to rules.

### Observed
- Regex extraction is high-precision for explicit statements but weak on implicit facts.
- Correction prefixes (`actually`, `I meant`) needed explicit handling to avoid duplicate conflicting actives.

---

## [0.4.0] - 2025-06-16 — Contradiction handling & supersession

### Added
- Supersession logic: new value for same key deactivates prior memory, sets `supersedes`, keeps history.
- Employment change patterns (`I work at X` → `I just joined Y`).

### Changed
- Recall now injects **active** user memories directly (boosted), so stale facts are not surfaced ahead of updates.

### Observed
- Stripe → Notion scenario: inactive Stripe memory retained with `active=false`; recall context shows only Notion.
- Opinion keys use broader buckets (`opinion.general`) to allow gradual evolution without hard overwrite.

---

## [0.5.0] - 2025-06-16 — Hybrid retrieval

### Added
- SQLite FTS5 lexical index with BM25 ranking.
- TF-IDF semantic similarity (offline, no embedding API).
- Reciprocal Rank Fusion + recency/type/active boosts.
- Context formatter respecting approximate `max_tokens` budget.

### Changed
- Moved away from initial TF-IDF-only prototype after exact-token probes (e.g. company names, city names) under-ranked paraphrased queries.

### Observed
- Pure semantic scoring missed exact matches like “Notion” vs “where does the user work”.
- FTS + fusion improved probe hit rate from ~50% to **≥75%** on fixtures.

---

## [0.6.0] - 2025-06-16 — Recall quality fixtures & tests

### Added
- `fixtures/recall_quality.py` with 4 scripted conversations and probe queries.
- `tests/test_recall_quality.py` reports aggregate expected-fact hit rate (threshold 75%).
- Persistence simulation test using on-disk SQLite file.

### Observed
- Berlin/NYC move scenario reliably returns Berlin and often the move event.
- Correction fixture (`Paris` → `Lyon`) required correction-prefix stripping in rules.

---

## [1.0.0] - 2025-06-16 — Release candidate

### Added
- README with architecture, tradeoffs, failure modes, and test instructions.
- `.env.example`, `.gitignore`, healthcheck in compose.

### Notes
- Ready for `docker compose up` with no manual DB migration steps (`create_all` on startup).
- LLM extraction remains optional; service is fully functional without external APIs.
