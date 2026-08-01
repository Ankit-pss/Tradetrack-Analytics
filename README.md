# TradeTrack

**A trading journal web app, and the analytics platform built on top of it.**

This repository contains two connected projects:

| | Project | What it is |
|---|---|---|
| 🖥️ | **[TradeTrack Journal](#-1-tradetrack-journal-the-web-app)** | A full-stack Flask + JavaScript app for logging and reviewing trades |
| 📊 | **[TradeTrack Analytics](TradeTrack-Analytics/)** | An end-to-end data analytics project — SQL warehouse, Python pipeline, ML model and interactive dashboard over 10,781 trades |

They are joined by [`import_journal.py`](TradeTrack-Analytics/python/import_journal.py),
which loads real trades out of the app's database and scores them with the same
KPI engine the analytics project uses.

```
┌────────────────────┐   import_journal.py   ┌──────────────────────────┐
│  TradeTrack        │ ────────────────────► │  TradeTrack Analytics    │
│  Journal (web app) │                       │  cleaning → SQL → ML →   │
│  server/ client/   │                       │  dashboard → insights    │
└────────────────────┘                       └──────────────────────────┘
```

---

# 📊 1. TradeTrack Analytics

> **[→ Full documentation in `TradeTrack-Analytics/README.md`](TradeTrack-Analytics/README.md)**

![Dashboard](TradeTrack-Analytics/images/dashboard_preview.png)

An end-to-end data analytics portfolio project analysing **10,781 closed trades**
across 12 traders, 6 instruments and 7 strategies.

| Metric | Value | | Metric | Value |
|---|---|---|---|---|
| Closed trades | **10,781** | | Profit factor | **1.07** |
| Net P&L | **+$220,184** | | Sharpe / Sortino | **0.80 / 0.95** |
| Win rate | **35.13%** | | Max drawdown | **14.50%** |

**What it contains**

- **SQL** — star-schema SQLite warehouse, 21 commented analytical queries
  (gaps-and-islands streak detection, window-function drawdown curves,
  `LAG` growth), all **executed on every pipeline run**
- **Python** — a market + behaviour simulation, a cleaning pipeline with a
  documented decision per defect, 77 engineered features, and a KPI/risk library
- **Machine learning** — a leakage-controlled classifier with 31 post-close
  columns hard-banned by a runtime assertion, and a model card that states
  plainly where the model fails
- **Dashboard** — a zero-dependency dark fintech dashboard: 6 animated KPI cards,
  10 interactive charts, 5 live filters, no build step and no CDN
- **Power BI** — 368 lines of DAX, an importable theme, and a page-by-page spec
- **Insights** — 20 business findings, every number computed rather than typed

```bash
cd TradeTrack-Analytics
pip install -r requirements.txt
python python/run_all.py          # full pipeline, ~30 seconds
open dashboard/index.html
```

The pipeline is fully deterministic — a complete regeneration reproduces every
published figure exactly.

### Analysing your own journal data

```bash
python TradeTrack-Analytics/python/import_journal.py --capital 5000
```

Reads `server/database.db`, maps it into the analytical schema, and reports the
same KPIs. It honours the app's `quantity / 100 = 1 unit` convention (reading
`quantity` literally would report every P&L 100× too large) and **reconciles the
stored P&L against a recomputation** to prove the mapping is right.

It also refuses to flatter you: on a small journal it prints the sample-size,
missing-fee and coverage warnings *before* the numbers, because a 13-trade
Sharpe ratio of 11.9 is arithmetically correct and practically meaningless.

---

# 🖥️ 2. TradeTrack Journal (the web app)

A premium full-stack web application for logging, tracking and reviewing trades,
with a cyberpunk/glassmorphism UI.

## Features


- **Dashboard** — live P&L, win rate, best/worst trades, interactive equity curve
- **Trade logging** — assets, entry/exit, stoploss, targets, risk/reward,
  strategies, and screenshot uploads
- **Analytics** — profit factor and expectancy, drawdown and streaks,
  breakdowns by asset/strategy/weekday/session, mistake-tag tracking and
  automated warnings (overtrading, sizing)
- **Calendar view** — monthly grid of daily P&L
- **Filtering** — date range, asset and strategy across all views

## Tech stack

- **Frontend** — HTML5, vanilla JavaScript, Tailwind CSS (CDN), Chart.js
- **Backend** — Python 3, Flask, SQLite3
- **Design** — Orbitron / JetBrains Mono, neon glow, glassmorphism

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install Flask Werkzeug

cd server
python app.py
```

Then open **http://127.0.0.1:5001**. The backend initialises the SQLite
database on first run and serves the frontend from `client/`.

## API endpoints

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/stats` | Basic statistics and equity curve data |
| `GET` | `/api/trades` | List trades (supports filtering) |
| `POST` | `/api/trades` | Add a trade |
| `PUT` | `/api/trades/<id>` | Update or close a trade |
| `DELETE` | `/api/trades/<id>` | Delete a trade |
| `GET` | `/api/analytics` | Advanced metrics and automated insights |

### A known data issue

The app writes **two different timestamp formats** — `2026-04-22T14:30:48` from
the server and `2026-04-21T22:15` (no seconds) from the browser's
`datetime-local` input. The importer parses both and reports the count, but a
naive reader would silently drop those rows from every time-based analysis.
Worth normalising at the write path.

---

## Repository layout

```
trading-journal/
├── client/                     web app frontend
├── server/                     Flask API + SQLite database
├── TradeTrack-Analytics/       the analytics project  ◄── start here
│   ├── data/ sql/ python/ notebooks/
│   ├── dashboard/ powerbi/ reports/ images/
│   └── README.md
└── README.md
```

## License

MIT — see [TradeTrack-Analytics/LICENSE](TradeTrack-Analytics/LICENSE).
