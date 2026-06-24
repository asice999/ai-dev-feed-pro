import os
import requests
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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
        model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content


if __name__ == "__main__":
    repos = fetch_repos()
    report = summarize(repos)
    print("\n🔥 GitHub AI Weekly Report\n")
    print(report)
