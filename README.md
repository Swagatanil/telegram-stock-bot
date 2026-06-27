# 📈 NSE Stock Screener Telegram Bot

A Telegram bot that screens the Indian stock market (NSE) for stocks showing
**high price gains with unusually low delivery percentage** — a pattern
often associated with speculative/intraday-driven price moves. Users can
also select specific stocks from the daily list and receive **live
intraday price updates every 15 minutes** during market hours.

## 🎯 Problem It Solves

Retail traders often want a quick way to spot stocks where the price moved
up sharply but most of the volume was *intraday trading* rather than
*delivery-based buying* (i.e., low delivery %). Manually checking this
across 1800+ NSE stocks every day isn't practical — this bot automates the
entire workflow and delivers a clean, ranked list straight to Telegram.

## ✨ Features

- **Daily automated screening** — fetches NSE's official end-of-day
  "bhavcopy" data, filters EQ-series stocks with positive price change and
  delivery % below a configurable threshold, and ranks the top movers.
- **On-demand command** — `/top20` fetches a fresh list anytime.
- **Interactive stock selection** — inline Telegram buttons let the user
  pick which stocks to follow further.
- **Live intraday tracking** — for selected stocks, the bot polls NSE's
  live quote API every 15 minutes during trading hours (9:15 AM–3:30 PM
  IST, Mon–Fri) and pushes price/% change updates.
- **Resilient data fetching** — automatically falls back to the previous
  trading day if data isn't available yet (handles weekends/holidays).
- **Scheduled jobs** — built on `python-telegram-bot`'s JobQueue for both
  the daily screening run and the 15-minute intraday loop.

## 🛠️ Tech Stack

| Layer              | Tools / Libraries                          |
|---------------------|---------------------------------------------|
| Language            | Python 3                                    |
| Bot framework       | `python-telegram-bot` (async, v20+)         |
| Data processing     | `pandas`                                    |
| HTTP / scraping      | `requests` (with session/cookie handling)   |
| Scheduling          | `JobQueue` (APScheduler under the hood)     |
| Data source         | NSE official bhavcopy archive + live quote API |
| Persistence         | JSON file (lightweight, no DB needed)       |

## 🏗️ Architecture

```
┌─────────────────┐      daily (7 PM IST)      ┌──────────────────────┐
│  NSE Bhavcopy    │ ───────────────────────▶  │   Screening Engine    │
│  (EOD CSV data)   │                            │  (pandas filter/sort) │
└─────────────────┘                            └──────────┬────────────┘
                                                            │
                                                            ▼
                                              ┌──────────────────────┐
                                              │   Telegram Bot Layer  │
                                              │  (commands + buttons) │
                                              └──────────┬────────────┘
                                                            │
                                          user selects stocks via inline buttons
                                                            │
                                                            ▼
┌─────────────────┐    every 15 min (market hrs)  ┌──────────────────────┐
│ NSE Live Quote   │ ◀───────────────────────────  │  Intraday Tracker Job │
│  API              │ ───────────────────────────▶  │  (sends updates)      │
└─────────────────┘                                └──────────────────────┘
```

## 🚀 Setup & Usage

```bash
git clone https://github.com/<your-username>/telegram-stock-bot.git
cd telegram-stock-bot
pip install -r requirements.txt

# Set environment variables
export BOT_TOKEN="your_telegram_bot_token"
export CHAT_ID="your_telegram_chat_id"

python bot.py
```

Then in Telegram:
- `/start` — see available commands
- `/top20` — get today's top gainers with low delivery %, with buttons to
  select stocks for 15-minute intraday tracking

## 🔍 Key Engineering Challenges Solved

- **NSE anti-scraping behavior** — NSE requires a valid session/cookie
  obtained from its homepage before archive/API endpoints respond; handled
  via a shared `requests.Session`.
- **Changing data source URLs** — NSE migrated its bhavcopy archive domain;
  the fetcher is structured so the base URL is a single constant, easy to
  update.
- **Stale/missing EOD data on weekends & holidays** — the fetcher walks
  backwards day-by-day until it finds the last valid trading day's file.
- **Stateful per-user selection in an async bot** — implemented using
  Telegram's `CallbackQueryHandler` with inline keyboards, persisting
  confirmed selections to disk so tracking survives bot restarts.

## 📌 Disclaimer

This project is a **market data screening tool** built for educational and
personal-automation purposes. It does **not** provide investment advice or
buy/sell recommendations.

## 🔮 Possible Future Improvements

- Add a proper database (SQLite/Postgres) instead of JSON for multi-user
  scale
- Add unit tests for the filtering logic
- Dockerize for easier deployment
- Add volume-spike and 52-week-high/low filters
