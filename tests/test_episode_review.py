from fastapi.testclient import TestClient
from app import main


def test_review_roundtrip_does_not_touch_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ensure_project", lambda pid: {"id": pid})
    monkeypatch.setattr(main.storage, "project_file", lambda pid, name: tmp_path / name)
    asset = tmp_path / "content.md"
    asset.write_text("original", encoding="utf-8")
    client = TestClient(main.app)
    assert client.get("/api/projects/1/episode-review").json() == {"card": {}, "releases": []}
    response = client.put("/api/projects/1/episode-review", json={"audience_question": "  为什么要看  "})
    assert response.status_code == 200
    assert response.json()["card"]["audience_question"] == "为什么要看"
    assert client.get("/api/projects/1/episode-review").json()["card"]["updated_at"]
    assert asset.read_text(encoding="utf-8") == "original"
    assert client.put("/api/projects/1/episode-review", json={"viewer_takeaway": "x" * 4001}).status_code == 422
