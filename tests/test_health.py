"""Health endpoint readiness checks."""


def test_health_ready_when_db_and_fts_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["fts"] == "ok"
