import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import generate

import json


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


def test_fetch_github_captures_language_and_topics(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "items": [
                    {
                        "full_name": "test/repo",
                        "description": "desc",
                        "stargazers_count": 100,
                        "html_url": "https://github.com/test/repo",
                        "language": "Python",
                        "topics": ["ai", "machine-learning"],
                    }
                ]
            }

    def fake_get(url, params, headers, timeout):
        captured["data"] = True
        return FakeResponse()

    monkeypatch.setattr(generate.requests, "get", fake_get)

    repos = generate.fetch_github()

    assert repos[0]["language"] == "Python"
    assert repos[0]["topics"] == ["ai", "machine-learning"]


def test_ai_analyze_fallback_produces_rich_fields():
    items = [
        {
            "title": "owner/repo",
            "desc": "An AI-powered code completion tool for developers",
            "stars": 1234,
            "url": "https://github.com/owner/repo",
            "source": "GitHub",
            "language": "Python",
            "topics": ["ai", "developer-tools", "code-generation"],
        }
    ]

    with patch.object(generate.client.chat.completions, "create", side_effect=Exception("blocked")):
        result = generate.ai_analyze(items)

    assert len(result) == 1
    r = result[0]
    assert r["core_features"]
    assert r["use_cases"]
    assert r["tech_stack"]
    assert r["highlights"]
    assert len(r["core_features"]) > 20
    assert r["language"] == "Python"
    assert r["topics"] == ["ai", "developer-tools", "code-generation"]


def test_telegram_message_uses_rich_format(monkeypatch):
    items = [
        {
            "title": "owner/repo",
            "stars": 1234,
            "stars_fmt": "1,234",
            "core_features": "AI驱动的代码补全工具，支持多种编程语言",
            "use_cases": "日常编码、代码审查、批量重构",
            "tech_stack": "Python + Transformer + VS Code 插件",
            "highlights": "准确率高，支持上下文感知补全",
            "url": "https://github.com/owner/repo",
            "source": "GitHub",
            "score": 8.5,
            "category": "Developer-Tools",
        }
    ]
    sent = []

    monkeypatch.setattr(generate.requests, "post", lambda url, json, timeout: sent.append(json) or None)
    monkeypatch.setattr(generate.os, "getenv", lambda k, d=None: {
        "TELEGRAM_BOT_TOKEN": "tok",
        "TELEGRAM_CHAT_ID": "cid",
        **os.environ,
    }.get(k, ""))

    generate.send_telegram(items)

    assert len(sent) >= 1
    msg = sent[0]["text"]
    assert "1. <b>owner/repo</b>" in msg
    assert "Star 数量：1,234" in msg
    assert "核心功能" in msg
    assert "AI驱动的代码补全工具" in msg
    assert "适用场景" in msg
    assert "技术栈" in msg
    assert "Python + Transformer" in msg
    assert "亮点特色" in msg
    assert "准确率高" in msg
    assert "项目地址" in msg
    assert "github.com/owner/repo" in msg


def test_main_uses_rich_format_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setattr(generate, "DATA_FILE", tmp_path / "feed.json")
    monkeypatch.setattr(generate, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(generate, "fetch_github", lambda: [{
        "title": "owner/repo",
        "desc": "An AI tool",
        "stars": 88,
        "url": "https://github.com/owner/repo",
        "source": "GitHub",
        "language": "TypeScript",
        "topics": ["ai"],
    }])
    monkeypatch.setattr(generate, "fetch_producthunt", lambda: [])
    monkeypatch.setattr(generate, "send_telegram", lambda items: None)

    generate.main()

    feed = json.loads((tmp_path / "feed.json").read_text())
    assert feed[0]["core_features"]
    assert feed[0]["tech_stack"]
    assert feed[0]["highlights"]