def test_health_endpoint(client, monkeypatch):
    async def available():
        return False

    monkeypatch.setattr("app.api.routes.health.local_llm_service.is_available", available)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database_status": "available",
        "ai_provider_available": False,
    }
