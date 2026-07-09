#!/usr/bin/env python3
"""AI Trend Radar — GitHub + Product Hunt + AI + TG."""
import json, os, re, time, sys
import requests
from pathlib import Path
from openai import OpenAI
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "feed.json"
HISTORY_FILE = ROOT / "data" / "history.json"

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)


# ---- GitHub ----

def fetch_github():
    print("[github] fetching trending repos...")
    url = "https://api.github.com/search/repositories"
    gh_token = os.getenv("GITHUB_TOKEN")
    headers = {"Authorization": f"Bearer {gh_token}"} if gh_token else {}
    since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    params = {"q": f"created:>{since} stars:>50", "sort": "stars", "order": "desc", "per_page": 8}
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    items = r.json().get("items", [])
    repos = []
    for i in items:
        repos.append({
            "title": i["full_name"],
            "desc": i.get("description") or "",
            "stars": i["stargazers_count"],
            "url": i["html_url"],
            "source": "GitHub",
        })
    print(f"[github] got {len(repos)} repos")
    return repos


# ---- Product Hunt ----

def fetch_producthunt():
    token = os.getenv("PH_DEV_TOKEN")
    if not token:
        print("[ph] PH_DEV_TOKEN not set, trying scrape...")
        return fetch_ph_scrape()
    return fetch_ph_api(token)


def fetch_ph_api(token):
    print("[ph] using API v2...")
    query = """
    query {
      posts(first: 10, order: VOTES) {
        edges { node {
          id name tagline url votesCount commentsCount createdAt
          topics(first: 3) { edges { node { name } } }
        }}
      }
    }"""
    resp = requests.post(
        "https://api.producthunt.com/v2/api/graphql",
        json={"query": query},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    data = resp.json()
    if "errors" in data:
        print(f"[ph] API error: {data['errors']}")
        return []
    edges = data.get("data", {}).get("posts", {}).get("edges", [])
    items = []
    for e in edges:
        node = e["node"]
        topics = [t["node"]["name"] for t in node.get("topics", {}).get("edges", [])]
        items.append({
            "title": node["name"],
            "desc": node.get("tagline") or "",
            "stars": node.get("votesCount", 0),
            "url": node["url"],
            "source": "ProductHunt",
            "topics": topics,
            "comments": node.get("commentsCount", 0),
        })
    print(f"[ph] got {len(items)} products via API")
    return items


def fetch_ph_scrape():
    print("[ph] scraping homepage...")
    try:
        resp = requests.get(
            "https://www.producthunt.com/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; TrendRadar/1.0)"},
            timeout=30,
        )
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
        if not match:
            print("[ph] scrape failed: no __NEXT_DATA__")
            return []
        data = json.loads(match.group(1))
        posts = (data.get("props", {}).get("apolloState", {}) or {})
        items = []
        seen = set()
        for key, val in posts.items():
            if not key.startswith("Post:"):
                continue
            name = val.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            topics = []
            for te in val.get("topics", {}).get("edges", []):
                tn = te.get("node", {}).get("name", "")
                if tn:
                    topics.append(tn)
            items.append({
                "title": name,
                "desc": val.get("tagline") or "",
                "stars": val.get("votesCount", 0),
                "url": f"https://www.producthunt.com/posts/{val.get('slug','')}",
                "source": "ProductHunt",
                "topics": topics,
                "comments": val.get("commentsCount", 0),
            })
        print(f"[ph] scraped {len(items)} products")
        return items
    except Exception as e:
        print(f"[ph] scrape error: {e}")
        return []


# ---- AI Analysis ----

def local_analyze(items):
    """Deterministic fallback so the feed still updates when the AI endpoint is down."""
    analyzed = []
    for idx, it in enumerate(items):
        desc = (it.get("desc") or "").strip()
        title = it.get("title", "")
        text = f"{title} {desc}".lower()
        if any(k in text for k in ("ai", "llm", "agent", "model", "gpt")):
            category = "AI"
        elif any(k in text for k in ("dev", "code", "github", "api", "tool", "cli", "sdk")):
            category = "Developer-Tools"
        elif any(k in text for k in ("design", "ui", "figma")):
            category = "Design"
        elif any(k in text for k in ("learn", "course", "tutorial")):
            category = "Learning"
        elif any(k in text for k in ("saas", "startup")):
            category = "SaaS"
        else:
            category = "Other"
        stars = int(it.get("stars") or 0)
        score = max(1, min(10, round(5 + min(stars, 5000) / 1000, 1)))
        summary = desc[:20] if desc else title[:20]
        analyzed.append({
            "id": idx,
            "title": title,
            "summary": summary,
            "category": category,
            "score": score,
            "reason": "热度较高" if stars else "值得关注",
            "source": it.get("source", ""),
            "stars": stars,
            "url": it.get("url", ""),
        })
    print(f"[ai] fallback analyzed {len(analyzed)} items")
    return analyzed


def ai_analyze(items):
    if not items:
        return []
    lines = []
    for idx, it in enumerate(items):
        src_tag = f"[{it['source']}]"
        lines.append(
            f"ID:{idx} | {src_tag} | {it['title']}\n"
            f"  描述: {it['desc']}\n"
            f"  热度: {it['stars']}\n"
            f"  链接: {it['url']}"
        )
    prompt = f"""分析以下 GitHub + Product Hunt 热门项目，逐条输出 JSON 数组。

每个对象字段:
- id: 整数(ID编号)
- title: 字符串(项目名)
- summary: 字符串(中文一句话总结，20字内)
- category: 字符串(分类: AI/Developer-Tools/Productivity/Design/Learning/SaaS/DevOps/Other)
- score: 数字(0-10综合评分)
- reason: 字符串(为什么火，15字内)
- source: 字符串(保持输入里的source值)

输入:
{chr(10).join(lines)}

只输出 JSON 数组，不要 markdown 代码块。"""
    try:
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        text = resp.choices[0].message.content.strip()
        json_text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text).strip()
        result = json.loads(json_text)
        # Merge stars + url from original items (AI may not output these)
        for r in result:
            idx = r.get("id")
            if idx is not None and 0 <= idx < len(items):
                r.setdefault("stars", items[idx].get("stars", 0))
                r.setdefault("url", items[idx].get("url", ""))
        print(f"[ai] analyzed {len(result)} items")
        return result
    except Exception as exc:
        raw_txt = text if 'text' in dir() else 'N/A'
        print(f"[ai] error: {exc}, raw: {str(raw_txt)[:200]}")
        return local_analyze(items)


# ---- Merge with history ----

def load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {}


def save_history(h):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")


def merge_history(analyzed):
    old = load_history()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = []
    for it in analyzed:
        key = it.get("title", "")
        prev = old.get(key, {})
        history = prev.get("history", [])
        prev_stars = history[-1]["stars"] if history else 0
        growth = it.get("stars", 0) - prev_stars
        history.append({"day": today, "stars": it.get("stars", 0)})
        if len(history) > 90:
            history = history[-90:]
        result.append({**it, "growth": growth, "history": history})
        old[key] = {
            "stars": it.get("stars", 0),
            "history": history,
            "source": it.get("source", ""),
        }
    save_history(old)
    return result


# ---- Save ----

def save_data(items):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[save] {len(items)} items -> data/feed.json")


# ---- Telegram ----

def send_telegram(items):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[tg] not configured, skip")
        return
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    lines = [f"🤖 <b>AI Trend Radar</b> — {now}\n"]
    for it in items[:10]:
        src_emoji = "🐙" if it.get("source") == "GitHub" else "🟠"
        lines.append(
            f"{src_emoji} <b>{it['title']}</b>\n"
            f"  {it.get('summary','')} | ⭐{it.get('score','?')} | {it.get('category','')}\n"
            f"  {it.get('reason','')}\n"
            f"  <a href='{it.get('url','')}'>🔗 链接</a>\n"
        )
    text = "\n".join(lines)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    max_len = 4000
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        requests.post(url, json={
            "chat_id": chat_id, "text": text[:split_at], "parse_mode": "HTML"
        }, timeout=15)
        text = text[split_at:]
    requests.post(url, json={
        "chat_id": chat_id, "text": text, "parse_mode": "HTML"
    }, timeout=15)
    print("[tg] sent")


# ---- Main ----

def main():
    gh = fetch_github()
    ph = fetch_producthunt()
    all_items = gh + ph
    if not all_items:
        print("[main] no items fetched, exiting")
        sys.exit(1)
    analyzed = ai_analyze(all_items)
    if not analyzed:
        print("[main] AI analysis returned empty, exiting")
        sys.exit(1)
    merged = merge_history(analyzed)
    save_data(merged)
    send_telegram(merged)
    print("[main] done")


if __name__ == "__main__":
    main()
