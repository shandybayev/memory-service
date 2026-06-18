# Changelog

All notable changes to this memory service implementation.

## [1.0.0] - 2025-06-16 — Initial release

### Why

The challenge required a single deployable service with a fixed HTTP contract, durable memory, and demonstrable fact evolution within a 48-hour window. A SQLite monolith with synchronous ingest was chosen to keep the transaction boundary simple and guarantee immediate recall after `POST /turns`.

Hybrid retrieval was introduced because exact keyword queries (company names, cities) needed lexical search, while broader phrasing benefited from TF-IDF similarity. Reciprocal rank fusion merged both channels without depending on an embedding API.

### Result

A working end-to-end path: ingest turns, extract structured memories with supersession, index into FTS5, and serve recall/search under session and user scope.

### Added
- FastAPI monolith with the full HTTP contract: `/health`, `/turns`, `/recall`, `/search`, `GET /users/{id}/memories`, and session/user deletes.
- SQLite persistence with WAL, FTS5 indexing, and a Docker named volume at `/data`.
- Rule-based memory extraction with optional LLM assist (`OPENAI_API_KEY`); rules-only when unset.
- Supersession for fact evolution (e.g. Stripe → Notion employment change).
- Hybrid retrieval: FTS5 lexical search, per-request TF-IDF similarity, and reciprocal rank fusion.
- Context formatter with `max_tokens` budget; recall and search scoping (`session OR user`).
- Pytest suite including contract, supersession, malformed input, persistence, and recall-quality fixtures.

---

## [1.1.0] - 2025-06-16 — Contract hardening

### Why

Testing uncovered edge cases around retrieval scope alignment, malformed FTS input, supersession ordering under concurrency, and unscoped search behavior. These paths could return wrong results, leak cross-tenant data, or crash the service if left unhandled.

### Result

Retrieval scope is consistent across lexical and similarity channels. Poison FTS queries and invalid search input fail safely. Supersession is atomic per key. `/health` reports readiness before traffic is accepted.

### Fixed
- Lexical and similarity retrieval share the same scope (`session OR user`, not `AND`).
- FTS malformed and poison queries return empty hits instead of HTTP 500.
- Supersession deactivates the prior row before insert; partial unique index on active `(user_id, key)` with retry on conflict.
- Recall filters turn snippets that repeat superseded fact values.

### Added
- `/health` readiness probes for database and FTS (`503` when degraded).
- Search rejects queries with no alphanumeric tokens (`422`).
- Tests for DELETE endpoints, cross-session recall, and FTS poison queries.

### Changed
- Unscoped `POST /search` returns HTTP `200` with empty `results` (contract-compliant).

---

## [1.2.0] - 2025-06-16 — Extraction and retrieval polish

### Why

Recall-quality fixtures showed gaps in regex coverage for common phrasing (employment changes, move statements) and in how active memories were packed into context. LLM output parsing also needed a single safe fallback path when JSON was malformed.

### Result

Higher hit rate on scripted scenarios. Recall context uses token budget more efficiently by injecting only query-relevant active memories.

### Added
- Expanded rule patterns (employment, location, move phrasing including `moved to X from Y`).
- `LLMExtractor.parse_response_content` with safe JSON fallback.
- Parametrized extraction tests and mocked LLM failure paths.

### Changed
- Recall injects query-matched active memories only (better `max_tokens` packing).
- Context formatter labels preferences and opinions correctly.

---

## [1.3.0] - 2025-06-16 — Live verification

### Why

Unit tests validated logic in-process but did not exercise the same Docker image and volume layout used at evaluation time. A repeatable end-to-end script was needed to confirm all seven endpoints, persistence across container restart, and key scenarios (location change, employment supersession).

### Result

One command verifies health, ingest, recall, search, memories, DELETE, and restart persistence against the live container.

### Added
- `scripts/smoke_docker.sh` and `scripts/smoke_docker.ps1` for end-to-end Docker checks (health, Berlin/NYC, Stripe→Notion, search, DELETE).
- Container restart persistence check in the smoke scripts.

---

## [1.4.0] - 2025-06-16 — Submission

### Why

The challenge spec defines port 8080 as the default endpoint for evaluation. Documentation was consolidated so the repository presents a clear evaluator path (`docker compose up -d` → `/health` → `localhost:8080`) without internal working artifacts.

### Result

Default port, healthcheck, smoke scripts, and docs are aligned with the spec. README and changelog describe the final behavior only.

### Changed
- Default service port set to **8080** per challenge spec (`docker-compose.yml`, `Dockerfile`, smoke scripts, docs).
- README and changelog trimmed for submission.

### Removed
- Internal working documents from the repository root.
