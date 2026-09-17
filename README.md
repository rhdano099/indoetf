# Bhavcopy — Right Horizons markets desk

Static site (`index.html`) + a scheduled GitHub Action that keeps `data/etf-history.json`
fresh with real NSE ETF prices via `yfinance` (no API key needed).

## One-time setup

1. Create a new **public** GitHub repo (Pages needs public on the free plan, unless you
   have GitHub Pro/Team/Enterprise for private-repo Pages).
2. Push these files to it (root of the repo — don't nest them in a subfolder):
   - `index.html`
   - `data/etf-history.json`
   - `scripts/fetch_etf_data.py`
   - `.github/workflows/update-data.yml`
3. Repo **Settings → Pages** → Source: "Deploy from a branch" → Branch: `main`, folder `/ (root)` → Save.
   GitHub gives you a URL like `https://<username>.github.io/<repo>/` within a minute or two.
4. Repo **Settings → Actions → General** → under "Workflow permissions", select
   **"Read and write permissions"** and save (the Action needs this to commit the data file back).
5. Repo **Actions** tab → find "Update ETF data" → **Run workflow** (the ▶ button) to fetch data
   for the first time instead of waiting for the schedule.
6. Once it finishes (~1–2 min), `data/etf-history.json` will be populated. Confirm at
   `https://<username>.github.io/<repo>/data/etf-history.json`.
7. Open your site (`https://<username>.github.io/<repo>/`) → ETF Tracker tab → paste
   `https://<username>.github.io/<repo>/data/etf-history.json` into the "Connect live data" box → Connect.

After that, it re-fetches automatically on the schedule in `update-data.yml`
(weekdays shortly after NSE close) — no key, no manual work.

## Updating the site itself

If you ask Claude for further changes to the dashboard, re-export `index.html` and
push it over the existing one — the data pipeline is unaffected.
