## Learned User Preferences

- Prefers a static GitHub Pages opportunity scanner (HTML/CSS/JS) with scheduled Actions data refresh — not Flutter and not trading/wallet execution.
- Opportunity focus includes cheap “Buy No” setups (low Yes odds with No ask around ~95¢ or cheaper), not only Buy Yes edge.
- Scanner filters should have hover tooltips; disable filters that only apply to the opposite Side when they have no effect.
- Results table should show time until market close (hours/minutes), allow sort by time to close, and show forecasted min/max temps to one decimal place.

## Learned Workspace Facts

- Project is TempEdge: a read-only Polymarket daily-temperature scanner comparing market prices to Open-Meteo GFS ensemble bucket probabilities.
- Pipeline: `scripts/refresh.py` pulls Polymarket Gamma daily-temperature events + Open-Meteo ensembles, scores edge as modelProb − ask/mid, writes `data/opportunities.json` and `data/markets.json`.
- City airports, timezones, and °C/°F units live in `config/cities.json`; UI is `index.html` + `assets/`.
- GitHub Actions workflow `.github/workflows/refresh-data.yml` refreshes on a ~5-minute cron (GitHub minimum) and workflow_dispatch, commits data, and deploys Pages. Site “Refresh data” opens the Actions workflow page for a manual Run workflow.
- Model Yes % is the fraction of ensemble members whose forecast high/low falls in that market’s temperature bucket (histogram), not a calibrated probability from Polymarket.
