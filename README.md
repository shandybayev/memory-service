# Memory Service

A Dockerized memory service for AI agents. It ingests completed conversation turns, extracts structured memories, indexes them for hybrid retrieval, and serves recall context for the next agent turn.

## Quick start

```bash
docker compose up --build
```

Service listens on `http://localhost:8000`.

Copy `.env.example` to `.env` if you want optional LLM extraction (`OPENAI_API_KEY`). Without it, deterministic rule-based extraction is used.

### Smoke test

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/turns -H "Content-Type: application/json" -d '{
  "session_id": "demo",
  "user_id": "alice",
  "messages": [
    {"role": "user", "content": "I just moved from NYC to Berlin."},
    {"role": "assistant", "content": "Welcome to Berlin!"}
  ],
  "timestamp": "2025-06-01T12:00:00Z"
}'

curl -X POST http://localhost:8000/recall -H "Content-Type: application/json" -d '{
  "query": "Where does this user live?",
  "session_id": "demo",
  "user_id": "alice",
  "max_tokens": 1024
}'

curl http://localhost:8000/users/alice/memories
```

Data persists across `docker compose down && docker compose up` via the `memory_data` named volume mounted at `/data`.

## Architecture

Single-service FastAPI monolith with clear layers:

```
src/
  api/            # HTTP contract (routes, schemas)
  core/           # config, logging, errors
  db/             # SQLAlchemy models + SQLite session
  services/
    extraction/   # rule + optional LLM memory extraction
    retrieval/    # lexical FTS + TF-IDF semantic + fusion
    formatting/   # recall context packing
    indexing.py   # sync search index + FTS
    turn_service.py
    recall_service.py
    memory_service.py
```

**Flow**

1. `POST /turns` persists the turn, runs synchronous extraction, indexes memories and snippets.
2. `POST /recall` loads active user facts, runs hybrid search, packs readable context under `max_tokens`.
3. `GET /users/{id}/memories` returns structured memory objects (not raw chat).

## Backing store

**SQLite + WAL** on a Docker volume (`/data/memory.db`).

Why SQLite:

- Zero external dependencies for `docker compose up`
- Fast to ship; survives restarts with a named volume
- Native **FTS5** for lexical retrieval (Porter stemmer)

Tables:

- `turns` — raw conversation turns (JSON messages)
- `memories` — structured extracted memories with supersession
- `search_documents` — unified retrieval index
- `search_fts` — FTS5 virtual table over document content

## Extraction pipeline

Hybrid extractor:

1. **Rule-based (default)** — regex patterns for employment, location, preferences, opinions, pets/family, moves, and corrections (`actually`, `I meant`).
2. **Optional LLM** — if `OPENAI_API_KEY` is set, merges higher-confidence LLM extractions with rules. On failure or missing key, rules-only.

Each memory has `type`, normalized `key`, `value`, `confidence`, provenance (`source_session`, `source_turn`), and `search_text`.

## Recall strategy

Hybrid retrieval (not vector-only):

| Signal | Method |
|--------|--------|
| Lexical | SQLite FTS5 + BM25 rank |
| Semantic | TF-IDF cosine (word + bigram) |
| Fusion | Reciprocal Rank Fusion |
| Boosts | active facts, memory type, recency, query-token overlap |

`POST /recall` prioritizes packed context:

1. Stable active user facts
2. Query-relevant memories
3. Recent conversation snippets (when token budget allows; stale superseded facts filtered out)

Lexical and semantic channels share the same scope: documents match **session OR user** when both IDs are provided.

`POST /search` requires at least one of `session_id` or `user_id` to prevent cross-tenant leakage.

## Fact evolution

When a new memory shares a `key` with an active memory but a different `value`:

- Old memory: `active=false`, kept for history
- New memory: `active=true`, `supersedes=<old_id>`
- A partial unique index enforces one active memory per `(user_id, key)`
- Recall and search boost active facts; stale values are deprioritized

Example: “I work at Stripe” → “I just joined Notion” yields active `Notion`, superseded `Stripe`.

## Tradeoffs

| Choice | Benefit | Cost |
|--------|---------|------|
| SQLite monolith | Simple deploy, persistent volume | Not ideal for very high write QPS |
| Rule extraction | Deterministic, no API key | Misses nuanced implicit facts |
| TF-IDF vs embeddings API | Offline, fast, exact-token friendly | Weaker paraphrase matching than large embeddings |
| Sync extraction/indexing | Immediate consistency after `POST /turns` | Turn latency includes extraction |

## Failure modes

- **Missing `user_id`** — turn stored, but no memories extracted (anonymous turns).
- **Malformed JSON / validation errors** — `422`, service stays up.
- **Oversized payload** — `413` when body exceeds `MAX_TURN_PAYLOAD_BYTES`.
- **LLM errors** — logged, falls back to rules.
- **Empty recall** — returns `{ "context": "", "citations": [] }`.

## Running tests

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -v
```

Test coverage:

- Contract roundtrip (`tests/test_contract.py`)
- Persistence simulation (`tests/test_persistence.py`)
- Session/user isolation (`tests/test_isolation.py`)
- Malformed input (`tests/test_malformed.py`)
- Supersession (`tests/test_supersession.py`)
- Recall quality fixture (`tests/test_recall_quality.py`) — reports hit rate on scripted conversations in `fixtures/`
- DELETE endpoints (`tests/test_delete.py`)
- Cross-session recall (`tests/test_cross_session_recall.py`)

Docker persistence test:

```bash
docker compose up --build -d
# POST a turn, then:
docker compose down
docker compose up -d
# recall should still return prior facts
```

## API summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| POST | `/turns` | Ingest turn + extract + index |
| POST | `/recall` | Formatted context for next turn |
| POST | `/search` | Structured search results |
| GET | `/users/{user_id}/memories` | All structured memories |
| DELETE | `/sessions/{session_id}` | Delete session data |
| DELETE | `/users/{user_id}` | Delete user data |
