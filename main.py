import os
import requests
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


def fetch_repos():
    url = "https://api.github.com/search/repositories"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    params = {
        "q": "stars:>5000",
        "sort": "stars",
        "order": "desc",
        "per_page": 5,
    }
    r = requests.get(url, params=params, headers=headers)
    items = r.json()["items"]
    repos = []
    for i in items:
        repos.append(
            {
                "name": i["name"],
                "desc": i["description"] or "",
                "stars": i["stargazers_count"],
                "url": i["html_url"],
            }
        )
    return repos


def summarize(repos):
    prompt = "请用中文总结以下GitHub项目：\n\n"
    for r in repos:
        prompt += f"""
项目：{r['name']}
描述：{r['desc']}
stars：{r['stars']}
链接：{r['url']}
---
"""
    prompt += """
要求：
- 每个项目一句话说明
- 为什么火
- 适合谁
- Markdown输出
"""
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "code-top"), messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content


def send_telegram(text):
    """Send message via Telegram Bot API, auto-split if > 4096 chars."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, skip Telegram push")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    max_len = 4000  # leave margin
    chunks = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:]
    chunks.append(text)
    for i, chunk in enumerate(chunks):
        prefix = f"📬 ({i+1}/{len(chunks)})\n" if len(chunks) > 1 else ""
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": prefix + chunk,
            "parse_mode": "HTML",
        })
        if not resp.json().get("ok"):
            print(f"Telegram send error: {resp.text}")


if __name__ == "__main__":
    repos = fetch_repos()
    report = summarize(repos)
    title = "\n🔥 GitHub AI Weekly Report\n"
    print(title)
    print(report)
    send_telegram(report)
