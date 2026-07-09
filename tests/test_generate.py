import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import generate


def test_fetch_github_queries_repositories_created_within_last_7_days(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"items": []}

    def fake_get(url, params, headers, timeout):
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(generate.requests, "get", fake_get)

    generate.fetch_github()

    query = captured["params"]["q"]
    created_after = query.split("created:>", 1)[1].split(" ", 1)[0]
    created_date = generate.datetime.strptime(created_after, "%Y-%m-%d").date()
    today = generate.datetime.now(generate.timezone.utc).date()

    assert (today - created_date).days == 7


def test_ai_analyze_uses_local_fallback_when_openai_returns_non_json():
    items = [
        {
            "title": "owner/repo",
            "desc": "A useful AI developer tool",
            "stars": 123,
            "url": "https://github.com/owner/repo",
            "source": "GitHub",
        }
    ]

    with patch.object(generate.client.chat.completions, "create", side_effect=Exception("blocked html")):
        result = generate.ai_analyze(items)

    assert len(result) == 1
    assert result[0]["title"] == "owner/repo"
    assert result[0]["stars"] == 123
    assert result[0]["url"] == "https://github.com/owner/repo"
    assert result[0]["source"] == "GitHub"
    assert result[0]["score"] > 0


def test_main_can_continue_without_producthunt_when_github_has_items(monkeypatch, tmp_path):
    monkeypatch.setattr(generate, "DATA_FILE", tmp_path / "feed.json")
    monkeypatch.setattr(generate, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(generate, "fetch_github", lambda: [{
        "title": "owner/repo",
        "desc": "A useful AI developer tool",
        "stars": 88,
        "url": "https://github.com/owner/repo",
        "source": "GitHub",
    }])
    monkeypatch.setattr(generate, "fetch_producthunt", lambda: [])
    monkeypatch.setattr(generate, "send_telegram", lambda items: None)
    monkeypatch.setattr(generate, "ai_analyze", lambda items: [{
        "id": 0,
        "title": "owner/repo",
        "summary": "开发工具",
        "category": "Developer-Tools",
        "score": 7,
        "reason": "增长快",
        "source": "GitHub",
        "stars": 88,
        "url": "https://github.com/owner/repo",
    }])

    generate.main()

    assert (tmp_path / "feed.json").exists()
