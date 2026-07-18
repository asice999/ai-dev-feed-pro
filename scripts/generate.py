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
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
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
            "forks": i.get("forks_count", 0),
            "url": i["html_url"],
            "source": "GitHub",
            "language": i.get("language") or "",
            "topics": i.get("topics", []),
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

def _fmt_stars(n):
    """Format star count like '1,234'."""
    return f"{n:,}"


def local_analyze(items):
    """Rich deterministic fallback with core_features, use_cases, tech_stack, highlights."""
    CAT_RULES = [
        ("ai", "AI"), ("llm", "AI"), ("agent", "AI"), ("model", "AI"), ("gpt", "AI"),
        ("chatgpt", "AI"), ("openai", "AI"), ("machine learning", "AI"),
        ("dev", "Developer-Tools"), ("code", "Developer-Tools"), ("github", "Developer-Tools"),
        ("api", "Developer-Tools"), ("tool", "Developer-Tools"), ("cli", "Developer-Tools"),
        ("sdk", "Developer-Tools"), ("programming", "Developer-Tools"), ("ide", "Developer-Tools"),
        ("compiler", "Developer-Tools"), ("terminal", "Developer-Tools"),
        ("design", "Design"), ("ui", "Design"), ("figma", "Design"), ("ux", "Design"),
        ("learn", "Learning"), ("course", "Learning"), ("tutorial", "Learning"),
        ("saas", "SaaS"), ("startup", "SaaS"),
        ("productivity", "Productivity"), ("note", "Productivity"), ("organize", "Productivity"),
        ("mac", "macOS"), ("ios", "iOS"), ("app", "macOS"),
        ("chrome", "Browser-Extension"), ("extension", "Browser-Extension"),
    ]
    CAT_CN = {
        "AI": "AI", "Developer-Tools": "开发者工具", "Design": "设计",
        "Learning": "学习", "SaaS": "SaaS", "Productivity": "效率工具",
        "macOS": "macOS", "iOS": "iOS", "Browser-Extension": "浏览器扩展",
        "Other": "其他",
    }
    USE_CASE_MAP = {
        "AI": "AI 应用开发、智能客服、自动化流程、内容生成",
        "Developer-Tools": "日常开发、DevOps 自动化、代码质量提升",
        "Design": "UI/UX 设计、原型制作、设计系统管理",
        "Learning": "在线学习、技能培训、知识管理",
        "SaaS": "企业服务、团队协作、数据分析",
        "Productivity": "个人效率管理、团队协作、文档管理",
        "macOS": "mac 桌面应用、效率工具",
        "iOS": "iOS 移动应用、工具类 App",
        "Browser-Extension": "浏览器功能扩展、网页自动化",
        "Other": "通用工具、开源项目",
    }

    analyzed = []
    for idx, it in enumerate(items):
        desc = (it.get("desc") or "").strip()
        title = it.get("title", "")
        text_lower = f"{title} {desc}".lower()
        repo_name = title.split("/")[-1] if "/" in title else title
        lang = it.get("language") or ""
        topics = it.get("topics", [])
        stars = int(it.get("stars") or 0)

        # Category
        category = "Other"
        for kw, cat in CAT_RULES:
            if kw in text_lower:
                category = cat
                break

        cat_cn = CAT_CN.get(category, category)
        score = max(1, min(10, round(3.5 + (min(stars, 10000) ** 0.35) * 0.7, 1)))

        # core_features — expand desc into a full sentence
        if desc:
            core_features = f"{desc}。项目名称 {repo_name}，属于 {cat_cn} 类别。"
        else:
            core_features = f"{repo_name} 是一个 {cat_cn} 开源项目。"

        # use_cases
        use_cases = USE_CASE_MAP.get(category, "通用工具、开源社区使用")

        # tech_stack
        if lang:
            topic_tags = "、".join(t[:12] for t in topics[:4]) if topics else ""
            tech_stack = lang
            if topic_tags:
                tech_stack += f" + {topic_tags}"
        else:
            tech_stack = "多语言支持"

        # highlights
        if stars >= 1000:
            highlights = f"Star 数突破 {_fmt_stars(stars)}，社区活跃度高，增长迅猛"
        elif stars >= 300:
            highlights = f"Star 数 {_fmt_stars(stars)}，功能完善，获得开发者广泛认可"
        elif stars >= 100:
            highlights = f"Star 数 {_fmt_stars(stars)}，近期热门项目，值得关注"
        else:
            highlights = f"新晋项目，Star 数 {_fmt_stars(stars)}，发展潜力大"

        # reason — used as summary line at top of rich format
        if stars >= 500:
            reason = f"🔥 爆款！⭐{_fmt_stars(stars)}"
        elif stars >= 200:
            reason = f"⭐{_fmt_stars(stars)} 高热度项目"
        elif stars >= 100:
            reason = f"⭐{_fmt_stars(stars)} 热门项目"
        elif stars >= 50:
            reason = f"⭐{_fmt_stars(stars)} 增长中"
        else:
            reason = f"⭐{_fmt_stars(stars)} 新项目"

        summary = desc if desc else f"{repo_name} — {cat_cn} 开源项目"
        if len(summary) > 80:
            summary = summary[:77] + "..."

        analyzed.append({
            "id": idx,
            "title": title,
            "summary": summary,
            "category": category,
            "score": score,
            "reason": reason,
            "source": it.get("source", ""),
            "stars": stars,
            "url": it.get("url", ""),
            "language": lang,
            "topics": topics,
            "core_features": core_features,
            "use_cases": use_cases,
            "tech_stack": tech_stack,
            "highlights": highlights,
            "stars_fmt": _fmt_stars(stars),
            "forks": it.get("forks", 0),
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
            f"  语言: {it.get('language','')}\n"
            f"  标签: {', '.join(it.get('topics',[]))}\n"
            f"  链接: {it['url']}"
        )
    prompt = f"""分析以下 GitHub + Product Hunt 热门项目，逐条输出 JSON 数组。

每个对象字段:
- id: 整数(ID编号)
- title: 字符串(项目名)
- summary: 字符串(中文一句话总结)
- category: 字符串(分类: AI/Developer-Tools/Productivity/Design/Learning/SaaS/DevOps/Other)
- score: 数字(0-10综合评分)
- reason: 字符串(为什么火)
- source: 字符串(保持输入里的source值)
- core_features: 字符串(核心功能介绍，50-120字中文)
- use_cases: 字符串(适用场景，20-60字中文)
- tech_stack: 字符串(技术栈，20-60字)
- highlights: 字符串(亮点特色，40-80字中文)

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
        # Merge metadata from original items
        for r in result:
            idx = r.get("id")
            if idx is not None and 0 <= idx < len(items):
                orig = items[idx]
                r.setdefault("stars", orig.get("stars", 0))
                r.setdefault("url", orig.get("url", ""))
                r.setdefault("language", orig.get("language", ""))
                r.setdefault("topics", orig.get("topics", []))
                r.setdefault("stars_fmt", _fmt_stars(orig.get("stars", 0)))
                r.setdefault("forks", orig.get("forks", 0))
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


def _cooldown_hours(stars, forks):
    """推送频率：收藏和fork项目(≥5000★+≥100 fork) → 12h, 每周热点(≥1000★) → 168h(7d), 每月热点(<1000★) → 720h(30d)."""
    if stars >= 5000 and forks >= 100:
        return 6
    if stars >= 1000:
        return 168
    return 720

def _type_label(stars, forks):
    """返回项目类型标签"""
    if stars >= 5000 and forks >= 100:
        return "📌 收藏和fork"
    if stars >= 1000:
        return "🔥 每周热点"
    return "🌙 每月热点"

def _hours_since_last(now_iso, last_shown):
    """计算上次推送后过了几小时。"""
    if not last_shown:
        return 9999
    fmt = "%Y-%m-%dT%H"
    last = datetime.strptime(last_shown[:13], fmt)
    now = datetime.strptime(now_iso[:13], fmt)
    return (now - last).total_seconds() / 3600

def merge_history(analyzed):
    old = load_history()
    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H")
    today = now.strftime("%Y-%m-%d")
    result = []
    for it in analyzed:
        key = it.get("title", "")
        stars = it.get("stars", 0)
        forks = it.get("forks", 0)
        prev = old.get(key, {})
        history = prev.get("history", [])
        last_shown = prev.get("last_shown")
        cd = _cooldown_hours(stars, forks)
        hours_since = _hours_since_last(now_iso, last_shown)

        # 冷却期内 → 跳过本次推送（只更新星数历史）
        if hours_since < cd:
            prev_stars = history[-1]["stars"] if history else 0
            if prev_stars != stars:
                history.append({"day": today, "stars": stars})
                # dedup same-day entries
                keep = []
                for h in history:
                    if len(keep) < 2 or h["day"] != keep[-1]["day"]:
                        keep.append(h)
                    else:
                        keep[-1]["stars"] = max(keep[-1]["stars"], h["stars"])
                history = keep[-90:]
            old[key] = {
                "stars": stars, "history": history,
                "forks": forks, "source": it.get("source", ""),
                "last_shown": last_shown,
            }
            print(f"[freq] skip {key} (cooldown {cd}h, last {last_shown})")
            continue

        # 推送
        type_label = _type_label(stars, forks)
        prev_stars = history[-1]["stars"] if history else 0
        growth = stars - prev_stars
        history.append({"day": today, "stars": stars})
        if len(history) > 90:
            history = history[-90:]
        result.append({**it, "growth": growth, "history": history, "type_label": type_label})
        old[key] = {
            "stars": stars, "history": history,
            "forks": forks, "source": it.get("source", ""),
            "last_shown": now_iso,
        }
        print(f"[freq] push {key} (cooldown {cd}h, stars {stars})")

    save_history(old)
    print(f"[freq] {len(result)} pushed, {len(analyzed) - len(result)} skipped (cooldown)")
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
    for idx, it in enumerate(items[:10], 1):
        tl = it.get("type_label", "")
        lines.append(
            f"{idx}. {tl} <b>{it['title']}</b>\n"
            f"Star 数量：{it.get('stars_fmt', it.get('stars', ''))}\n"
            f"核心功能：{it.get('core_features', it.get('summary', ''))}\n"
            f"适用场景：{it.get('use_cases', '')}\n"
            f"技术栈：{it.get('tech_stack', '')}\n"
            f"亮点特色：{it.get('highlights', '')}\n"
            f"项目地址：{it.get('url', '')}\n"
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
