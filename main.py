import json
import os
import re
import sys
from pathlib import Path

import requests
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

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


def fetch_repos():
    """Fetch top GitHub repos by stars (from last 7 days)."""
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
                "language": i.get("language") or "Unknown",
                "url": i["html_url"],
            }
        )
    return repos


def analyze_repos(repos):
    """Use AI to summarize + categorize + score, output structured JSON."""
    cats = ", ".join(CATEGORIES)
    prompt = f"""Analyze these GitHub repositories and return a JSON array. For each repo pick one category from: {cats}.

Repos:
"""
    for r in repos:
        prompt += f"- {r['name']} | ⭐{r['stars']} | {r['desc']} | url: {r['url']}\n"

    prompt += """
Return ONLY a JSON array (no markdown, no code fences, no extra text). Each object must have:
- "title": repo name (string)
- "summary": one-sentence Chinese summary, include why it's trending (string)
- "category": one of the listed categories (string)
- "score": relevance score 0-10, based on AI/dev impact (number)
- "stars": star count (number)
- "url": repo url (string)

Example format:
[{"title":"foo/bar","summary":"...","category":"AI/ML","score":9.2,"stars":5000,"url":"https://github.com/foo/bar"}]
"""

    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "code-top"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return resp.choices[0].message.content


def parse_json(raw: str):
    """Robust JSON extraction from AI response."""
    # Try direct parse
    text = raw.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from ```json ... ``` block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try finding the first [ ... ] array
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    print(f"Failed to parse JSON. Raw response:\n{raw[:500]}", file=sys.stderr)
    return []


def format_markdown(items):
    """Convert structured data to human-readable Markdown for Telegram."""
    lines = ["🔥 *GitHub AI Weekly Report*\n"]
    for i in items:
        cat = i.get("category", "Other")
        score = i.get("score", 0)
        fire = "🟢" if score >= 8 else ("🟡" if score >= 6 else "🔵")
        lines.append(
            f"{fire} *{i['title']}*  ⭐{i.get('stars',0)}\n"
            f"_{cat}_ | 评分: {score}\n"
            f"{i['summary']}\n"
            f"[🔗 GitHub]({i['url']})"
        )
        lines.append("")  # blank line
    return "\n".join(lines)


def save_data(items):
    """Save structured data to storage/latest.json."""
    Path("storage").mkdir(exist_ok=True)
    with open("storage/latest.json", "w") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def send_telegram(text):
    """Send message via Telegram Bot API, auto-split if > 4096 chars."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, skip Telegram push")
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
            print(f"Telegram send error: {resp.text}")


if __name__ == "__main__":
    repos = fetch_repos()
    if not repos:
        print("No repos fetched, exiting.")
        sys.exit(1)

    print(f"Fetched {len(repos)} repos, analyzing with AI...")
    raw = analyze_repos(repos)
    items = parse_json(raw)

    if items:
        save_data(items)
        print(f"Saved {len(items)} items to storage/latest.json")

        md = format_markdown(items)
        print(md)
        send_telegram(md)
    else:
        print("No structured data generated.")
        sys.exit(1)
