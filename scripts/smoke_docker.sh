#!/usr/bin/env bash
# Live Docker smoke test — end-to-end verification against the real container.
# Requires: docker, curl, jq
# Usage (from repo root): bash scripts/smoke_docker.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="${BASE_URL:-http://localhost:8080}"
USER_ID="${SMOKE_USER_ID:-smoke-user}"
SESSION_ID="${SMOKE_SESSION_ID:-smoke-sess}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-90}"

pass() { echo "  OK: $1"; }
fail() { echo "FAIL: $1" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required but not found in PATH"
}

http_code() {
  local outfile="$1"
  shift
  curl -s -o "$outfile" -w "%{http_code}" "$@"
}

wait_for_health() {
  echo "Waiting for ${BASE_URL}/health (up to ${MAX_WAIT_SECONDS}s)..."
  local elapsed=0
  while [ "$elapsed" -lt "$MAX_WAIT_SECONDS" ]; do
    if body="$(curl -sf "${BASE_URL}/health" 2>/dev/null)"; then
      if echo "$body" | jq -e '.status == "ok" and .database == "ok" and .fts == "ok"' >/dev/null; then
        pass "health ready"
        return 0
      fi
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  fail "service did not become healthy in time"
}

post_turn() {
  local content="$1"
  local tmp
  tmp="$(mktemp)"
  local code
  code="$(http_code "$tmp" -X POST "${BASE_URL}/turns" \
    -H "Content-Type: application/json" \
    -d "{
      \"session_id\": \"${SESSION_ID}\",
      \"user_id\": \"${USER_ID}\",
      \"messages\": [
        {\"role\": \"user\", \"content\": \"${content}\"},
        {\"role\": \"assistant\", \"content\": \"Noted.\"}
      ],
      \"timestamp\": \"2025-06-01T12:00:00Z\"
    }")"
  [ "$code" = "201" ] || fail "POST /turns returned HTTP ${code}: $(cat "$tmp")"
  jq -e '.id' "$tmp" >/dev/null || fail "POST /turns missing id"
  rm -f "$tmp"
}

post_recall() {
  local query="$1"
  curl -sf -X POST "${BASE_URL}/recall" \
    -H "Content-Type: application/json" \
    -d "{
      \"query\": \"${query}\",
      \"session_id\": \"${SESSION_ID}\",
      \"user_id\": \"${USER_ID}\",
      \"max_tokens\": 1024
    }"
}

echo "=== Memory service live Docker smoke test ==="
require_cmd docker
require_cmd curl
require_cmd jq

echo "Starting stack..."
if body="$(curl -sf "${BASE_URL}/health" 2>/dev/null)" && \
   echo "$body" | jq -e '.status == "ok" and .database == "ok" and .fts == "ok"' >/dev/null 2>&1; then
  if [ "${SMOKE_SKIP_BUILD:-}" != "1" ]; then
    echo "Rebuilding image to pick up latest code..."
    docker compose up -d --build
  else
    echo "Service already healthy - ensuring containers are up (no rebuild)."
    docker compose up -d
  fi
else
  docker compose up -d --build
fi

wait_for_health

echo "Resetting prior smoke data (if any)..."
curl -sf -X DELETE "${BASE_URL}/users/${USER_ID}" -o /dev/null || true

echo "1. GET /health"
body="$(curl -sf "${BASE_URL}/health")"
echo "$body" | jq -e '.status == "ok" and .database == "ok" and .fts == "ok"' >/dev/null \
  || fail "health body unexpected: $body"
pass "GET /health"

echo "2. Berlin / NYC move — POST /turns"
post_turn "I just moved from NYC to Berlin."
pass "ingest Berlin move"

echo "3. POST /recall — Where does this user live?"
recall="$(post_recall "Where does this user live?")"
echo "$recall" | jq -e '.context | test("Berlin")' >/dev/null \
  || fail "recall context missing Berlin: $recall"
pass "recall contains Berlin"

echo "3b. Docker restart - persistence check"
docker compose restart >/dev/null
wait_for_health
recall="$(post_recall "Where does this user live?")"
echo "$recall" | jq -e '.context | test("Berlin")' >/dev/null \
  || fail "Berlin missing after container restart: $recall"
pass "Berlin recall survives container restart"

echo "4. Employment supersession - Stripe then Notion"
post_turn "I work at Stripe."
post_turn "I just joined Notion."
pass "ingest Stripe -> Notion"

echo "5. POST /recall — Where does the user work?"
recall="$(post_recall "Where does the user work?")"
echo "$recall" | jq -e '.context | test("Notion")' >/dev/null \
  || fail "recall context missing Notion: $recall"
echo "$recall" | jq -e '.context | test("Stripe") | not' >/dev/null \
  || fail "recall context still contains Stripe: $recall"
pass "recall prefers Notion over Stripe"

echo "6. GET /users/${USER_ID}/memories"
memories="$(curl -sf "${BASE_URL}/users/${USER_ID}/memories")"
echo "$memories" | jq -e \
  '[.[] | select(.key == "employment.company" and .active == true)] | any(.value | test("Notion"))' \
  >/dev/null || fail "no active Notion employment memory: $memories"
echo "$memories" | jq -e \
  '[.[] | select(.key == "location.residence" and .active == true)] | any(.value | test("Berlin"))' \
  >/dev/null || fail "no active Berlin residence memory: $memories"
pass "structured memories present"

echo "7. POST /search (scoped)"
search_tmp="$(mktemp)"
code="$(http_code "$search_tmp" -X POST "${BASE_URL}/search" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"Berlin\",\"session_id\":\"${SESSION_ID}\",\"user_id\":\"${USER_ID}\",\"limit\":5}")"
[ "$code" = "200" ] || fail "scoped search HTTP ${code}: $(cat "$search_tmp")"
jq -e '.results | length >= 1' "$search_tmp" >/dev/null \
  || fail "scoped search returned no results: $(cat "$search_tmp")"
rm -f "$search_tmp"
pass "scoped search returns results"

echo "8. POST /search (unscoped - expect empty results)"
unscoped_tmp="$(mktemp)"
code="$(http_code "$unscoped_tmp" -X POST "${BASE_URL}/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"Berlin","limit":5}')"
[ "$code" = "200" ] || fail "unscoped search HTTP ${code}: $(cat "$unscoped_tmp")"
jq -e '.results | length == 0' "$unscoped_tmp" >/dev/null \
  || fail "unscoped search should return empty results: $(cat "$unscoped_tmp")"
rm -f "$unscoped_tmp"
pass "unscoped search returns empty results (contract-safe)"

echo "9. DELETE /sessions/${SESSION_ID}"
del_sess_tmp="$(mktemp)"
code="$(http_code "$del_sess_tmp" -X DELETE "${BASE_URL}/sessions/${SESSION_ID}")"
[ "$code" = "204" ] || fail "DELETE session HTTP ${code}: $(cat "$del_sess_tmp")"
rm -f "$del_sess_tmp"
pass "DELETE session"

echo "10. DELETE /users/${USER_ID}"
del_user_tmp="$(mktemp)"
code="$(http_code "$del_user_tmp" -X DELETE "${BASE_URL}/users/${USER_ID}")"
[ "$code" = "204" ] || fail "DELETE user HTTP ${code}: $(cat "$del_user_tmp")"
rm -f "$del_user_tmp"
pass "DELETE user"

echo ""
echo "=== All smoke checks passed ==="
