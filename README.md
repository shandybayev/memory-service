# Memory Service

A Dockerized memory service for AI agents. It ingests conversation turns, extracts structured memories, indexes them for hybrid retrieval, and returns formatted recall context for the next agent turn.

---

## Quick start

From the repository root:

```bash
docker compose up -d
```

Wait until the service is healthy, then open **http://localhost:8080**:

```bash
curl http://localhost:8080/health
# {"status":"ok","database":"ok","fts":"ok"}
```

No `pip install`, database setup, or migrations are required. SQLite is created on first startup inside the container (`/data/memory.db` on the `memory_data` volume).

**Optional:** copy `.env.example` → `.env` and set `OPENAI_API_KEY` for LLM-assisted extraction. Without a key, extraction uses deterministic rules.

---

## Verify (smoke test)

End-to-end checks against the live container:

```bash
bash scripts/smoke_docker.sh
```

**Windows (PowerShell):**

```powershell
.\scripts\smoke_docker.ps1
```

Requires Docker. The bash script also needs `curl` and `jq`. Set `SMOKE_SKIP_BUILD=1` to skip image rebuild when the container is already up.

### Quick manual smoke

```bash
curl http://localhost:8080/health

curl -X POST http://localhost:8080/turns -H "Content-Type: application/json" -d '{
  "session_id": "demo",
  "user_id": "alice",
  "messages": [
    {"role": "user", "content": "I just moved from NYC to Berlin."},
    {"role": "assistant", "content": "Welcome to Berlin!"}
  ],
  "timestamp": "2025-06-01T12:00:00Z"
}'

curl -X POST http://localhost:8080/recall -H "Content-Type: application/json" -d '{
  "query": "Where does this user live?",
  "session_id": "demo",
  "user_id": "alice",
  "max_tokens": 1024
}'

curl http://localhost:8080/users/alice/memories
```

On Windows PowerShell, use `curl.exe` instead of `curl`.

Data survives `docker compose down` and `docker compose up -d` via the named volume. Use `docker compose down -v` to wipe data.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Readiness (DB + FTS); `503` if degraded |
| POST | `/turns` | Ingest turn, extract memories, index → `201 { "id" }` |
| POST | `/recall` | Formatted `context` + `citations` for next turn |
| POST | `/search` | Structured `results[]` (scoped); unscoped → empty `results` |
| GET | `/users/{user_id}/memories` | All structured memories (active + inactive) |
| DELETE | `/sessions/{session_id}` | Delete session data → `204` |
| DELETE | `/users/{user_id}` | Delete all user data → `204` |

---

## Architecture

### Design goals

| Goal | Approach |
|------|----------|
| Not a message log | `memories` table with typed, keyed facts and supersession |
| Immediate consistency | Extraction and indexing run synchronously in `POST /turns` before `201` |
| Hybrid recall | FTS5 lexical + TF-IDF similarity + RRF (not embedding top-k) |
| Container persistence | WAL SQLite on a Docker named volume |

### Layered monolith

```
┌─────────────────────────────────────────────────────────────┐
│  API (FastAPI)          routes.py, schemas.py               │
├─────────────────────────────────────────────────────────────┤
│  Orchestration          turn_service, recall_service        │
├──────────────┬──────────────────────┬─────────────────────┤
│  Extraction  │  Indexing            │  Retrieval          │
│  rules + LLM │  search_documents    │  FTS5 + TF-IDF      │
│  pipeline    │  + FTS5              │  + RRF + scope      │
├──────────────┴──────────────────────┴─────────────────────┤
│  Formatting             context.py (token-budget packing)   │
├─────────────────────────────────────────────────────────────┤
│  Persistence            SQLAlchemy → SQLite (/data)         │
└─────────────────────────────────────────────────────────────┘
```

### Ingest (`POST /turns`)

1. Persist turn to SQLite
2. Extract structured memories (rules; optional LLM if `OPENAI_API_KEY` is set)
3. Apply supersession for changed facts
4. Index memories and turn snippets into FTS5 and the search corpus
5. Commit and return `201`

Memories are queryable immediately after the response.

### Retrieval

| Layer | Implementation | Role |
|-------|----------------|------|
| Lexical | SQLite FTS5 + BM25 | Exact tokens: cities, company names |
| Similarity | Per-request TF-IDF + cosine | Bag-of-words overlap within scope |
| Fusion | Reciprocal Rank Fusion (RRF) | Merge ranked lists |

`POST /recall` formats hits under `max_tokens`. `POST /search` returns structured results. When both `session_id` and `user_id` are set, scope is `session OR user` (cross-session recall). Unscoped search returns `200` with `{"results":[]}`.

### Fact evolution

New value for the same `(user_id, key)` deactivates the old row and inserts an active replacement with a `supersedes` link. Example: "I work at Stripe" then "I joined Notion" — recall prefers Notion; `GET /users/{id}/memories` returns both rows.

### Extraction

- Runs on user messages only; skipped when `user_id` is null
- `timestamp` is optional on turns (server UTC default when omitted)
- Regex patterns cover employment, location, preferences, and similar; LLM path merges when configured
- Malformed FTS queries return empty hits (no `500`)

---

## Tradeoffs

| Decision | Why | Cost |
|----------|-----|------|
| SQLite monolith | No external deps; FTS5 built-in | Write throughput; no horizontal scale |
| Sync extract + index | Immediate recall after `201` | Turn latency bound to extraction |
| Regex-first extraction | Deterministic; no API key required | Misses implicit or nuanced facts |
| TF-IDF similarity | No model download | Weak paraphrase vs true embeddings |
| Turn snippet indexing | Recall works before extraction matches | `/search` may surface stale turn text |
| Unscoped search → empty | Contract-safe; no cross-tenant leakage | Callers must pass scope for results |
| No auth | Challenge scope | Production needs tenancy controls |

---

## Failure modes

| Condition | Behavior |
|-----------|----------|
| No matching data | `POST /recall` returns empty `context` and `citations`; `POST /search` returns empty `results` |
| Missing `OPENAI_API_KEY` | Service runs normally; rules-only extraction is used |
| Slow disk / SQLite latency | Turn ingestion latency increases (sync extract + index); correctness is preserved |
| Malformed search / FTS input | Empty results or `422` validation; service does not crash |
| Docker volume removed (`compose down -v`) | Empty database recreated on next startup; prior memories are lost |

---

## Configuration

All variables are optional. Defaults work inside Docker without a `.env` file.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite:////data/memory.db` | SQLite path (set in `docker-compose.yml`) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `MAX_TURN_PAYLOAD_BYTES` | `1048576` | Max `POST /turns` body size |
| `OPENAI_API_KEY` | (unset) | Enable LLM extraction; rules-only when empty |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model for LLM extraction |
| `RECENCY_WEIGHT` | `0.10` | Recency boost in retrieval |

See [.env.example](.env.example) for the full list.

---

## Tests

**Live Docker smoke:**

```bash
bash scripts/smoke_docker.sh
```

**Unit/integration tests** (optional, for local development):

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -v
```

| Suite | Coverage |
|-------|----------|
| `scripts/smoke_docker.*` | Live container: all 7 endpoints, Berlin/NYC, Stripe→Notion, restart persistence |
| `tests/test_contract.py` | Ingest → recall → memories shape |
| `tests/test_malformed.py` | Bad input, FTS poison queries |
| `tests/test_supersession.py` | Fact evolution |
| `tests/test_recall_quality.py` | Fixture conversations |
| `tests/test_persistence.py` | On-disk SQLite survives reinit |
| `tests/test_health.py` | `/health` readiness probes |
| `tests/test_delete.py` | Session/user deletion |

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.
