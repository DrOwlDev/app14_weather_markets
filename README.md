# TempEdge — Polymarket Weather Temperature Scanner

Static GitHub Pages app that ranks **Polymarket daily temperature** markets against **Open-Meteo GFS ensemble** probabilities so you can spot pricing edges.

Live category: [polymarket.com/weather/temperature](https://polymarket.com/weather/temperature)

## How it works

1. GitHub Actions runs `scripts/refresh.py` about every **5 minutes** (GitHub’s minimum schedule) and on manual dispatch.
2. The script pulls open daily-temperature events from the Polymarket Gamma API, fetches ensemble highs/lows for each city airport, histograms members into market buckets, and writes `data/opportunities.json`.
3. The static UI loads that JSON and lists opportunities sorted by absolute edge (`modelProb − bestAsk`).
4. Use **Refresh data** on the site to open the GitHub Actions workflow page, then click **Run workflow**.

No wallets or trading — read-only scanner.

## Local refresh

```bash
python scripts/refresh.py
```

Requires Python 3.10+ (stdlib only). Then open `index.html` via a local static server:

```bash
python -m http.server 8080
```

Visit `http://localhost:8080`.

## Deploy on GitHub Pages

1. Create a GitHub repo and push this project.
2. Settings → Pages → Source: **GitHub Actions**.
3. Allow the workflow write permission (Settings → Actions → General → Workflow permissions: Read and write).
4. Run **Refresh data and deploy Pages** from the Actions tab.

## Project layout

```
index.html              # scanner UI
assets/                 # CSS + JS
config/cities.json      # airport lat/lon, timezone, unit
data/                   # generated JSON snapshots
scripts/refresh.py      # fetch + score pipeline
.github/workflows/      # cron refresh + Pages deploy
```

## Interpreting edge

- **Positive edge**: ensemble implies a higher YES probability than the market ask — candidate to buy YES.
- **Negative edge**: market ask is rich vs the model — candidate to avoid YES / consider NO (not auto-traded here).
- Prefer rows with meaningful **liquidity** and edge beyond the spread (default filters: |edge| ≥ 5¢, liquidity ≥ 200).

Not financial advice. Station vs model grid mismatch and late-day path dependence can erase apparent edges.
