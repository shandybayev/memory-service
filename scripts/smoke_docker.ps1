# Live Docker smoke test - end-to-end verification against the real container.
# Requires: Docker, PowerShell 5.1+
# Usage (from repo root): .\scripts\smoke_docker.ps1

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$BaseUrl = if ($env:BASE_URL) { $env:BASE_URL } else { "http://localhost:8080" }
$UserId = if ($env:SMOKE_USER_ID) { $env:SMOKE_USER_ID } else { "smoke-user" }
$SessionId = if ($env:SMOKE_SESSION_ID) { $env:SMOKE_SESSION_ID } else { "smoke-sess" }
$MaxWaitSeconds = if ($env:MAX_WAIT_SECONDS) { [int]$env:MAX_WAIT_SECONDS } else { 90 }

function Pass($msg) { Write-Host "  OK: $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "FAIL: $msg" -ForegroundColor Red; exit 1 }

function Wait-ForHealth {
    Write-Host "Waiting for $BaseUrl/health (up to ${MaxWaitSeconds}s)..."
    $elapsed = 0
    while ($elapsed -lt $MaxWaitSeconds) {
        try {
            $body = Invoke-RestMethod -Uri "$BaseUrl/health" -UseBasicParsing
            if ($body.status -eq "ok" -and $body.database -eq "ok" -and $body.fts -eq "ok") {
                Pass "health ready"
                return
            }
        } catch { }
        Start-Sleep -Seconds 2
        $elapsed += 2
    }
    Fail "service did not become healthy in time"
}

function Post-Turn($content) {
    $payload = @{
        session_id = $SessionId
        user_id    = $UserId
        messages   = @(
            @{ role = "user"; content = $content }
            @{ role = "assistant"; content = "Noted." }
        )
        timestamp  = "2025-06-01T12:00:00Z"
    }
    $r = Invoke-WebRequest -Method POST -Uri "$BaseUrl/turns" `
        -ContentType "application/json" `
        -Body ($payload | ConvertTo-Json -Depth 5) `
        -UseBasicParsing
    if ($r.StatusCode -ne 201) { Fail "POST /turns HTTP $($r.StatusCode): $($r.Content)" }
    $id = ($r.Content | ConvertFrom-Json).id
    if (-not $id) { Fail "POST /turns missing id" }
}

function Post-Recall($query) {
    $payload = @{
        query      = $query
        session_id = $SessionId
        user_id    = $UserId
        max_tokens = 1024
    }
    return Invoke-RestMethod -Method POST -Uri "$BaseUrl/recall" `
        -ContentType "application/json" `
        -Body ($payload | ConvertTo-Json -Depth 5)
}

Write-Host "=== Memory service live Docker smoke test ===" -ForegroundColor Cyan

$alreadyHealthy = $false
try {
    $h = Invoke-RestMethod -Uri "$BaseUrl/health" -UseBasicParsing
    $alreadyHealthy = ($h.status -eq "ok" -and $h.database -eq "ok" -and $h.fts -eq "ok")
} catch { }

if ($alreadyHealthy -and $env:SMOKE_SKIP_BUILD -ne "1") {
    Write-Host "Rebuilding image to pick up latest code..."
    docker compose up -d --build
} elseif ($alreadyHealthy) {
    Write-Host "Service already healthy - ensuring containers are up (no rebuild)."
    docker compose up -d
} else {
    docker compose up -d --build
}

Wait-ForHealth

Write-Host "Resetting prior smoke data (if any)..."
try {
    Invoke-WebRequest -Method DELETE -Uri "$BaseUrl/users/$UserId" -UseBasicParsing | Out-Null
} catch { }

Write-Host "1. GET /health"
$health = Invoke-RestMethod -Uri "$BaseUrl/health" -UseBasicParsing
if ($health.status -ne "ok" -or $health.database -ne "ok" -or $health.fts -ne "ok") {
    Fail "health body unexpected: $($health | ConvertTo-Json -Compress)"
}
Pass "GET /health"

Write-Host "2. Berlin / NYC move - POST /turns"
Post-Turn "I just moved from NYC to Berlin."
Pass "ingest Berlin move"

Write-Host "3. POST /recall - Where does this user live?"
$recall = Post-Recall "Where does this user live?"
if ($recall.context -notmatch "Berlin") { Fail "recall context missing Berlin" }
Pass "recall contains Berlin"

Write-Host "3b. Docker restart - persistence check"
docker compose restart | Out-Null
Wait-ForHealth
$recall = Post-Recall "Where does this user live?"
if ($recall.context -notmatch "Berlin") { Fail "Berlin missing after container restart" }
Pass "Berlin recall survives container restart"

Write-Host "4. Employment supersession - Stripe then Notion"
Post-Turn "I work at Stripe."
Post-Turn "I just joined Notion."
Pass "ingest Stripe -> Notion"

Write-Host "5. POST /recall - Where does the user work?"
$recall = Post-Recall "Where does the user work?"
if ($recall.context -notmatch "Notion") { Fail "recall context missing Notion" }
if ($recall.context -match "Stripe") { Fail "recall context still contains Stripe" }
Pass "recall prefers Notion over Stripe"

Write-Host "6. GET /users/$UserId/memories"
$memories = Invoke-RestMethod -Uri "$BaseUrl/users/$UserId/memories" -UseBasicParsing
$activeNotion = $memories | Where-Object { $_.key -eq "employment.company" -and $_.active -eq $true -and $_.value -match "Notion" }
$activeBerlin = $memories | Where-Object { $_.key -eq "location.residence" -and $_.active -eq $true -and $_.value -match "Berlin" }
if (-not $activeNotion) { Fail "no active Notion employment memory" }
if (-not $activeBerlin) { Fail "no active Berlin residence memory" }
Pass "structured memories present"

Write-Host "7. POST /search (scoped)"
$searchBody = @{ query = "Berlin"; session_id = $SessionId; user_id = $UserId; limit = 5 } | ConvertTo-Json
$search = Invoke-RestMethod -Method POST -Uri "$BaseUrl/search" -ContentType "application/json" -Body $searchBody
if (-not $search.results -or $search.results.Count -lt 1) { Fail "scoped search returned no results" }
Pass "scoped search returns results"

Write-Host "8. POST /search (unscoped - expect empty results)"
$unscoped = @{ query = "Berlin"; limit = 5 } | ConvertTo-Json
$unscopedResult = Invoke-RestMethod -Method POST -Uri "$BaseUrl/search" -ContentType "application/json" -Body $unscoped
if ($unscopedResult.results -and $unscopedResult.results.Count -gt 0) {
    Fail "unscoped search should return empty results"
}
Pass "unscoped search returns empty results (contract-safe)"

Write-Host "9. DELETE /sessions/$SessionId"
$delSess = Invoke-WebRequest -Method DELETE -Uri "$BaseUrl/sessions/$SessionId" -UseBasicParsing
if ($delSess.StatusCode -ne 204) { Fail "DELETE session HTTP $($delSess.StatusCode)" }
Pass "DELETE session"

Write-Host "10. DELETE /users/$UserId"
$delUser = Invoke-WebRequest -Method DELETE -Uri "$BaseUrl/users/$UserId" -UseBasicParsing
if ($delUser.StatusCode -ne 204) { Fail "DELETE user HTTP $($delUser.StatusCode)" }
Pass "DELETE user"

Write-Host ""
Write-Host "=== All smoke checks passed ===" -ForegroundColor Green
