# Daily AI News Digest — Architecture & Operations Guide

## Overview

A production-ready Python service that runs **4 times daily (10 AM, 1 PM, 4 PM, 8 PM EDT)**, fetches top AI/ML news using OpenAI's web_search_preview tool, summarizes it with GPT-4o, and delivers a formatted HTML email digest via SendGrid.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                          main.py                                │
│  APScheduler cron: 10 AM, 1 PM, 4 PM, 8 PM EDT (4x daily)     │
│  BackgroundScheduler + sleep loop  ── python main.py --test    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ run_digest()
              ┌────────────▼────────────┐
              │     news_fetcher.py     │
              │  OpenAI Responses API   │
              │  tool: web_search_      │  ← OPENAI_API_KEY
              │    preview (gpt-4o)     │
              │  10 search query groups │
              │  Output: List[Article]  │
              │  (deduped, safety-filt) │
              └────────────┬────────────┘
                           │ articles: List[dict]
              ┌────────────▼────────────┐
              │      summarizer.py      │
              │  OpenAI Chat Completions│  ← OPENAI_API_KEY
              │  gpt-4o (no web search) │
              │  Clusters → 6 cats      │
              │  Picks Top 5 stories    │
              │  Output: DigestData     │
              └────────────┬────────────┘
                           │ digest_data: dict
              ┌────────────▼────────────┐
              │     email_builder.py    │
              │  Jinja2 render          │
              │  templates/digest_      │
              │    email.html           │
              │  Output: (subject, html)│
              └────────────┬────────────┘
                           │ (subject: str, html_body: str)
              ┌────────────▼────────────┐
              │     email_sender.py     │
              │  SendGrid SDK           │  ← SENDGRID_API_KEY
              │  Retry once on failure  │  ← FROM_EMAIL, TO_EMAIL
              │  (60s wait + retry)     │
              └─────────────────────────┘

  logs/digest.log  ──  RotatingFileHandler (5MB max, 3 backups)
```

---

## Prerequisites

### 1. OpenAI API Key
- Get your key at https://platform.openai.com/api-keys
- The `web_search_preview` built-in tool is enabled by default on `gpt-4o`
- Ensure your account has available credits at https://platform.openai.com/usage

### 2. SendGrid Setup
1. Create a free account at https://sendgrid.com (100 emails/day free)
2. **Verify your sender email**: Settings → Sender Authentication → Single Sender Verification
   - The `FROM_EMAIL` in `.env` MUST be a verified sender or SendGrid will reject the request
3. Create an API key: Settings → API Keys → Create API Key
   - Permission: **Mail Send (Full Access)** only — no other permissions needed

---

## Setup

```bash
# 1. Clone / copy project
cd /path/to/ai-news-generator

# 2. Create and activate virtual environment (Python 3.11+)
python3.11 -m venv venv
source venv/bin/activate         # macOS/Linux
# venv\Scripts\activate          # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure secrets
cp .env.example .env
nano .env                        # Fill in all 7 variables

# 5. Validate with a test run
python main.py --test
```

After `--test` completes:
- Check your inbox for the HTML digest
- Check `logs/digest.log` for the run log (article count, categories, send status)

---

## Running Locally

```bash
# One-shot test (full pipeline, no scheduler, then exits)
python main.py --test

# Start the scheduler daemon (blocks the terminal)
python main.py

# Background with nohup (keeps running after terminal closes)
nohup python main.py > /dev/null 2>&1 &
echo $! > /tmp/digest.pid        # Save PID to stop it later
kill $(cat /tmp/digest.pid)      # Stop it
```

All log output goes to both `logs/digest.log` and stdout.

---

## VPS Deployment (Ubuntu 22.04)

### Install Python 3.11

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

### Deploy the Application

```bash
# Copy project to server
scp -r /path/to/ai-news-generator/ user@your-vps:/opt/ai-news-digest/

# On the VPS:
cd /opt/ai-news-digest
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env    # Fill in real credentials
```

### systemd Service (Recommended — Auto-Restarts on Crash)

Create `/etc/systemd/system/ai-digest.service`:

```ini
[Unit]
Description=Daily AI News Digest
Documentation=file:///opt/ai-news-digest/CLAUDE.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/ai-news-digest
EnvironmentFile=/opt/ai-news-digest/.env
ExecStart=/opt/ai-news-digest/venv/bin/python main.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ai-digest

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable ai-digest
sudo systemctl start ai-digest

# Monitor
sudo systemctl status ai-digest
sudo journalctl -u ai-digest -f        # Tail live logs
sudo journalctl -u ai-digest --since "today"
```

### Keeping Alive with nohup (Simpler Alternative)

```bash
cd /opt/ai-news-digest
source venv/bin/activate
nohup python main.py >> logs/digest.log 2>&1 &
echo $! > /var/run/ai-digest.pid
```

---

## Cloud Deployment (Railway / Render)

Both platforms support always-on Python workers without OS-level cron — APScheduler handles scheduling internally.

### Procfile (both platforms)
```
worker: python main.py
```

### Railway
```bash
# Install Railway CLI
npm install -g @railway/cli

# Deploy
railway login
railway init
railway up

# Set environment variables in Railway dashboard:
# Project → Variables → Add all 7 from .env.example
```

### Render
1. Create a new **Background Worker** service (not Web Service)
2. Build command: `pip install -r requirements.txt`
3. Start command: `python main.py`
4. Set env vars in: Service → Environment → Add Environment Variable

**Note**: Free tier on both platforms may sleep after inactivity. Use a paid tier ($5–7/mo) or a cheap VPS for reliable daily execution.

---

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI platform API key | `sk-proj-...` |
| `SENDGRID_API_KEY` | SendGrid Mail Send key | `SG.xxx...` |
| `FROM_EMAIL` | Verified SendGrid sender address | `digest@yourdomain.com` |
| `TO_EMAIL` | Destination inbox | `you@gmail.com` |
| `SCHEDULE_HOURS` | Comma-separated 24h hours to fire | `10,13,16,20` |
| `SCHEDULE_MINUTE` | Minute past the hour to fire (0–59) | `0` |
| `SCHEDULE_TIMEZONE` | IANA timezone string | `America/New_York` |

---

## Safety Rules

These constraints are enforced in the codebase and must not be removed:

### 1. URL Integrity (No Hallucinated Links)
All article URLs in the digest must originate directly from OpenAI's `web_search_preview` tool response. The fetch prompt explicitly instructs the model: *"Only include URLs that were directly returned by your web_search tool calls. NEVER invent, guess, or hallucinate URLs."*

Rationale: Hallucinated URLs are either dead links or—worse—point to unintended/malicious content. Every link in the digest email must be a real article that was actually found by search.

### 2. Adversarial Content Filter
`news_fetcher._safety_filter()` rejects any article whose title or summary matches patterns associated with:
- HTML/script injection (`<script`, `<iframe`, `javascript:`)
- Prompt injection attempts (`ignore previous`, `ignore all`, `system prompt`, `you are now`, `disregard your`, `new instructions`, `act as`, `jailbreak`)

Rationale: Malicious actors can embed prompt injection payloads in article titles or descriptions indexed by search engines. These would be passed to the summarizer LLM and could manipulate its output. The filter is applied before any LLM processing.

### 3. No Paywalled or Authenticated Scraping
The BeautifulSoup fallback scraper (`news_fetcher._scrape_article_text()`) is only for public article pages. It does not follow redirects to login pages, does not handle authentication, and does not scrape content that requires an account. If a page requires auth, the scrape returns an empty string.

### 4. No Paid Scraping Services
The system uses Anthropic's `web_search` built-in tool exclusively for content discovery. No third-party news APIs (NewsAPI, Diffbot, etc.) are used. BeautifulSoup is only a summary-enrichment fallback for articles already discovered via web_search.

### 5. Disk Safety
`RotatingFileHandler` is configured with `maxBytes=5MB, backupCount=3`. Maximum disk usage for logs: ~15MB. The `logs/` directory is gitignored.

### 6. API Rate Discipline
Exactly 2 OpenAI API calls per digest run:
- Call 1: `news_fetcher.py` — Responses API with `web_search_preview`, model `gpt-4o`
- Call 2: `summarizer.py` — Chat Completions, `gpt-4o`, up to 4096 output tokens

At 4 runs per day: ~8 API calls/day, ~240/month — well within standard rate limits.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `AuthenticationError` from OpenAI | Invalid or missing API key | Check `OPENAI_API_KEY` in `.env` |
| `InsufficientQuotaError` from OpenAI | No OpenAI credits | Add credits at platform.openai.com/usage |
| `Forbidden` from SendGrid | FROM_EMAIL not verified | Complete Single Sender Verification in SendGrid dashboard |
| `0 articles fetched` | OpenAI API quota or network issue | Check `logs/digest.log` for API error details |
| Email goes to spam | FROM domain lacks SPF/DKIM | Set up domain authentication in SendGrid |
| APScheduler job never fires | Wrong timezone or hours config | Check `SCHEDULE_HOURS` and `SCHEDULE_TIMEZONE`, verify with `--test` flag |
| SSL errors on macOS | macOS Python missing CA certs | `certifi` fix is applied automatically in `main.py` |
| `FileNotFoundError: logs/` | `logs/` dir not created | `setup_logging()` calls `os.makedirs("logs", exist_ok=True)` — ensure `main.py` is the entry point |
