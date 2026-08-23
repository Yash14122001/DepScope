from fastapi.testclient import TestClient

from src.main import app


def test_health_endpoint():
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_rejects_unknown_session():
    response = TestClient(app).post("/api/ask", json={"session_id": "missing", "question": "What is this repo?"})

    assert response.status_code == 404


def test_quota_errors_are_reported_as_rate_limits(monkeypatch):
    from src import main
    from src.agent import AnalysisContext
    from src.call_graph import build_call_graph

    class QuotaError(Exception):
        def __str__(self):
            return "429 RESOURCE_EXHAUSTED retryDelay: 34s"

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(main, "run_agent", lambda *args, **kwargs: (_ for _ in ()).throw(QuotaError()))
    context = AnalysisContext(build_call_graph({}), files={})
    main.sessions["quota-test"] = main.RepositorySession("owner/repo", "main", {}, context)

    response = TestClient(app).post("/api/ask", json={"session_id": "quota-test", "question": "hi"})

    assert response.status_code == 429, response.text
    assert response.json()["detail"] == "Gemini API quota is exhausted. Try again in about 34 seconds."
    del main.sessions["quota-test"]