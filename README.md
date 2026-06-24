# 🤖 AI Trend Radar

GitHub Trending × AI Analysis — 24h Star Growth Radar

**Features**
- 🔍 GitHub 热门仓库抓取（stars > 1000）
- 🧠 AI 自动分类 + 评分（10 个类别）
- 📈 24h Star 增长追踪 + Chart.js 柱状图
- 📱 PWA 支持（Add to Home Screen）
- 📬 Telegram Bot 推送

**Architecture**

```
scripts/generate.py   ← 数据生成：fetch + AI + TG
data/feed.json        ← 结构化数据（自动提交）
frontend/             ← 纯静态前端（Cloudflare Pages）
```

**Deploy**

### 1. GitHub Actions（自动运行）
每 6 小时自动抓取，需配置 Secrets：
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`

### 2. Cloudflare Pages
1. 连接仓库 `asice999/ai-dev-feed-pro`
2. 构建目录：`frontend/`
3. 无需构建命令（纯静态）
4. 部署后获得 `*.pages.dev` 域名

**License**

MIT
