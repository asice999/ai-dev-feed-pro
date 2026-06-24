import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

DATA_FILE = "data/feed.json"
CATEGORIES = [
    "AI/ML",
    "Developer Tools",
    "Infrastructure",
    "Frontend",
    "Backend",
    "Data Science",
    "Security",
    "Mobile",
    "DevOps",
    "Learning",
    "Other",
]


def load_old_feed():
    """Load previous feed.json if exists, for growth comparison."""
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE) as f:
        items = json.load(f)
    return {i["title"]: i.get("stars", 0) for i in items}


def fetch_repos():
    url = "https://api.github.com/search/repositories"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    params = {
        "q": "stars:>1000",
        "sort": "stars",
        "order": "desc",
        "per_page": 10,
    }
    r = requests.get(url, params=params, headers=headers)
    data = r.json()
    if "items" not in data:
        print(f"GitHub API error: {data}", file=sys.stderr)
        return []
    repos = []
    for i in data["items"]:
        repos.append(
            {
                "name": i["full_name"],
                "desc": i["description"] or "(no description)",
                "stars": i["stargazers_count"],
                "forks": i.get("forks_count", 0),
                "language": i.get("language") or "Unknown",
                "url": i["html_url"],
                "created_at": i["created_at"][:10],
            }
        )
    return repos


def analyze_repos(repos):
    cats = ", ".join(CATEGORIES)
    prompt = f"""Analyze these GitHub repositories and return a JSON array. Pick one category per repo from: {cats}.

Repos:
"""
    for r in repos:
        prompt += f"- {r['name']} | ⭐{r['stars']} | lang: {r['language']} | {r['desc']} | url: {r['url']}\n"

    prompt += """
Return ONLY a JSON array (no markdown, no code fences). Each object:
- "title": repo full name (string)
- "summary": one-sentence Chinese summary, why trending (string)
- "category": one of the listed categories (string)
- "score": relevance 0-10 for AI/developer impact (number)
- "url": repo url (string)

Example:
[{"title":"owner/repo","summary":"一句话中文总结","category":"AI/ML","score":9.2,"url":"https://github.com/owner/repo"}]
"""
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "code-top"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return resp.choices[0].message.content


def parse_json(raw: str):
    text = raw.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    print(f"JSON parse failed. Raw:\n{raw[:500]}", file=sys.stderr)
    return []


def merge_data(items, old_feed, repos_lookup):
    """Merge AI analysis with repo metadata, compute growth from old feed."""
    today_str = datetime.now(timezone.utc).strftime("%m-%d")
    yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%m-%d")

    result = []
    for item in items:
        name = item["title"]
        repo = repos_lookup.get(name, {})
        stars = repo.get("stars", 0)
        old_stars = old_feed.get(name, stars)
        growth = max(0, stars - old_stars)

        entry = {
            "title": name,
            "summary": item["summary"],
            "category": item.get("category", "Other"),
            "score": item.get("score", 0),
            "stars": stars,
            "forks": repo.get("forks", 0),
            "language": repo.get("language", "Unknown"),
            "created_at": repo.get("created_at", ""),
            "url": item["url"],
            "growth": growth,
            "history": [
                {"day": yesterday_str, "stars": old_stars},
                {"day": today_str, "stars": stars},
            ],
            "updated": datetime.now(timezone.utc).isoformat(),
        }
        result.append(entry)

    # sort by growth desc
    result.sort(key=lambda x: x["growth"], reverse=True)
    return result


def save_data(items):
    Path("data").mkdir(exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def format_telegram(items):
    """Format structured data for Telegram Markdown."""
    lines = ["🔥 *AI Trend Radar*  —  24h Growth\n"]
    for i in items[:10]:
        growth = i.get("growth", 0)
        score = i.get("score", 0)
        fire = "🟢" if score >= 8 else ("🟡" if score >= 6 else "🔵")
        boom = " 🚀" if growth >= 500 else ""
        lines.append(
            f"{fire} *{i['title']}*  ⭐{i.get('stars',0)}  +{growth}{boom}\n"
            f"_{i['category']}_  |  评分 {score}\n"
            f"{i['summary']}\n"
            f"[🔗 GitHub]({i['url']})"
        )
        lines.append("")
    return "\n".join(lines)


def send_telegram(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ Telegram not configured, skip")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    max_len = 4000
    chunks = []
    remaining = text
    while len(remaining) > max_len:
        split_at = remaining.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    chunks.append(remaining)
    for i, chunk in enumerate(chunks):
        prefix = f"📬 ({i+1}/{len(chunks)})\n" if len(chunks) > 1 else ""
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": prefix + chunk,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
        )
        if not resp.json().get("ok"):
            print(f"Telegram error: {resp.text}")


if __name__ == "__main__":
    old_feed = load_old_feed()
    repos = fetch_repos()
    if not repos:
        print("No repos fetched, exiting.")
        sys.exit(1)

    repos_lookup = {r["name"]: r for r in repos}
    print(f"Fetched {len(repos)} repos, analyzing with AI...")
    raw = analyze_repos(repos)
    items = parse_json(raw)

    if not items:
        print("AI analysis failed.")
        sys.exit(1)

    merged = merge_data(items, old_feed, repos_lookup)
    save_data(merged)
    print(f"Saved {len(merged)} items to {DATA_FILE}")

    tg = format_telegram(merged)
    print(tg)
    send_telegram(tg)
