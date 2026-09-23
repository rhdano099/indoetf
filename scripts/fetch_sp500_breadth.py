"""
Fetch daily breadth statistics for the S&P 500, to power a 5th "S&P 500"
option on the site's Market Breadth tab -- full parity with the existing
Nifty 50 / Nifty 500 / Midcap 150 / Smallcap 250 options: same 4 indicators
(% above 200-day SMA, Net Highs (H-L), 52-Week Highs, 52-Week Lows), same
JSON shapes, no site-code changes needed beyond index.html's existing
generic PRICE_FILES/PCT_FILES wiring.

Computes, per trading day, across the full current S&P 500 constituent
list:
    - % of constituents trading above their own 200-day SMA
    - new 52-week highs (count)
    - new 52-week lows (count)
    - net highs-minus-lows

Also pulls the S&P 500 index level itself (^GSPC) for the price chart.

Constituent list: scraped from Wikipedia's "List of S&P 500 companies"
page (the standard, free, no-signup source most breadth trackers use) --
just 500 tickers, so unlike a full Nasdaq-Composite-style pull (~3,000+
stocks, 60-90 minutes) this finishes in a few minutes even pulling one
ticker at a time with pacing.

Usage:
    cd ~/Documents/<your-site-repo>   (wherever this site's scripts/ folder lives)
    pip install yfinance pandas lxml --break-system-packages   (if not already installed)
    python3 scripts/fetch_sp500_breadth.py [--sleep 0.5] [--resume]

Writes / updates (relative to this script's parent folder, i.e. the repo root):
    data/sp500-price.json           -- [["YYYY-MM-DD", indexLevel], ...]
    data/breadth-history-sp500.json -- [["YYYY-MM-DD", pctAbove200Sma], ...]
    data/breadth-extra-sp500.json   -- {"sp500": {dates, newHighs, newLows, netHL}} --
                                        a SEPARATE file, not a merge into
                                        breadth-extra.json (see the comment above
                                        the code that writes it for why). The
                                        GitHub Actions workflow merges this into
                                        the final data/breadth-extra.json.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HISTORY_YEARS = 2          # covers 200-day SMA + 52-week hi/lo with room to spare
CHECKPOINT_EVERY = 50


def load_sp500_tickers():
    """Scrape the current S&P 500 constituent list from Wikipedia (first
    table on the page). Falls back to a short hardcoded set of large,
    liquid S&P 500 names if the page can't be reached or its table shape
    changes, so the script still produces something usable rather than
    hard failing -- though a fallback run is a rough proxy, not a real
    500-stock breadth measure, and the script says so loudly if it has to
    use it."""
    try:
        tables = pd.read_html(WIKI_SP500_URL)
        df = tables[0]
        col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        tickers = sorted(set(str(t).strip().replace(".", "-") for t in df[col].dropna()))
        if len(tickers) < 400:
            raise ValueError(f"only found {len(tickers)} tickers -- table shape probably changed")
        print(f"Loaded {len(tickers)} S&P 500 constituents from Wikipedia")
        return tickers
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: could not load the S&P 500 list from Wikipedia ({e}).", file=sys.stderr)
        print("Falling back to a small hardcoded set of large S&P 500 names -- this will NOT "
              "produce a real S&P-500-wide breadth reading, only a rough placeholder. Re-run "
              "later once the page is reachable.", file=sys.stderr)
        return [
            "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "GOOG", "META", "BRK-B", "AVGO", "TSLA",
            "JPM", "LLY", "V", "UNH", "XOM", "PG", "MA", "COST", "HD", "JNJ",
            "MRK", "ABBV", "CVX", "BAC", "KO", "PEP", "ADBE", "CRM", "WMT", "AMD",
        ]


def pull_history(ticker, years, retries=3, base_wait=2.0):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            hist = yf.Ticker(ticker).history(period=f"{years}y", interval="1d", auto_adjust=True)
            if hist is None or hist.empty:
                return None
            hist = hist.reset_index()
            hist.columns = [str(c).lower() for c in hist.columns]
            if pd.api.types.is_datetime64tz_dtype(hist["date"]):
                hist["date"] = hist["date"].dt.tz_localize(None)
            return hist[["date", "close"]].rename(columns={"close": ticker})
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(base_wait * attempt)
    print(f"    FAILED {ticker}: {last_err}", file=sys.stderr)
    return None


def compute_breadth(price_panel: pd.DataFrame):
    """price_panel: DataFrame indexed by date, one column per ticker (close price).
    Returns (pct_above_sma200, extra) -- walk-forward, no lookahead: each day only
    uses data up to and including itself."""
    sma200 = price_panel.rolling(200, min_periods=200).mean()
    above = (price_panel > sma200)
    valid = sma200.notna() & price_panel.notna()
    n_valid = valid.sum(axis=1)
    n_above = (above & valid).sum(axis=1)
    pct_above = (n_above / n_valid.replace(0, np.nan) * 100).round(2)

    roll_high = price_panel.rolling(252, min_periods=100).max()
    roll_low = price_panel.rolling(252, min_periods=100).min()
    is_high = (price_panel >= roll_high) & price_panel.notna()
    is_low = (price_panel <= roll_low) & price_panel.notna()
    new_highs = is_high.sum(axis=1)
    new_lows = is_low.sum(axis=1)
    net_hl = new_highs - new_lows

    dates = [d.strftime("%Y-%m-%d") for d in price_panel.index]
    pct_series = [[d, v] for d, v in zip(dates, pct_above) if pd.notna(v)]
    extra = {
        "dates": dates,
        "newHighs": [int(x) for x in new_highs],
        "newLows": [int(x) for x in new_lows],
        "netHL": [int(x) for x in net_hl],
    }
    return pct_series, extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.5, help="seconds between ticker requests")
    ap.add_argument("--resume", action="store_true", help="skip tickers already in the checkpoint file")
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    checkpoint_path = DATA_DIR / "_sp500_prices_checkpoint.parquet"

    tickers = load_sp500_tickers()

    existing = pd.DataFrame()
    already_have = set()
    if args.resume and checkpoint_path.exists():
        existing = pd.read_parquet(checkpoint_path)
        already_have = set(existing.columns) - {"date"}
        tickers = [t for t in tickers if t not in already_have]
        print(f"Resuming: {len(already_have)} tickers already pulled, {len(tickers)} remaining")

    frames = [existing.set_index("date")] if not existing.empty else []
    failed = []

    for i, t in enumerate(tickers, 1):
        df = pull_history(t, HISTORY_YEARS)
        if df is None:
            failed.append(t)
        else:
            frames.append(df.set_index("date"))

        if i % 10 == 0 or i == len(tickers):
            print(f"[{i}/{len(tickers)}] {t}: {'ok' if df is not None else 'FAILED'}  ({len(failed)} failed so far)")

        if i % CHECKPOINT_EVERY == 0 and frames:
            panel = pd.concat(frames, axis=1)
            panel.reset_index().to_parquet(checkpoint_path, index=False)
            print(f"  ...checkpointed {panel.shape[1]} tickers to {checkpoint_path}")

        time.sleep(args.sleep)

    if not frames:
        print("No price data pulled at all -- aborting.", file=sys.stderr)
        sys.exit(1)

    panel = pd.concat(frames, axis=1).sort_index()
    panel.reset_index().to_parquet(checkpoint_path, index=False)
    print(f"\nPulled {panel.shape[1]} tickers, {len(panel)} trading days")

    pct_series, extra = compute_breadth(panel)
    (DATA_DIR / "breadth-history-sp500.json").write_text(json.dumps(pct_series))
    print(f"Wrote {DATA_DIR / 'breadth-history-sp500.json'} ({len(pct_series)} days)")

    # Write to a SEPARATE file rather than merging into breadth-extra.json directly.
    # This script runs as its own parallel GitHub Actions job alongside
    # fetch_live_data.py (which also writes breadth-extra.json for the 4 Nifty
    # indices), each in its own isolated checkout -- if both scripts tried to
    # read-modify-write the *same* file, whichever job's artifact got downloaded
    # last would silently clobber the other's data. The workflow's commit job
    # merges this file with the Nifty one after both jobs finish.
    (DATA_DIR / "breadth-extra-sp500.json").write_text(json.dumps({"sp500": extra}))
    print(f"Wrote {DATA_DIR / 'breadth-extra-sp500.json'} (merged into breadth-extra.json by the workflow)")

    print("\nFetching S&P 500 (^GSPC) index level for the price chart...")
    spx = pull_history("^GSPC", HISTORY_YEARS)
    if spx is not None:
        price_series = [[row["date"].strftime("%Y-%m-%d"), row["^GSPC"]] for _, row in spx.iterrows()]
        (DATA_DIR / "sp500-price.json").write_text(json.dumps(price_series))
        print(f"Wrote {DATA_DIR / 'sp500-price.json'} ({len(price_series)} days)")
    else:
        print("WARNING: could not fetch ^GSPC -- sp500-price.json not written.", file=sys.stderr)

    if failed:
        print(f"\n{len(set(failed))} tickers failed -- re-run with --resume to retry just those.")

    print("\nDone. Commit data/sp500-price.json, data/breadth-history-sp500.json, and the "
          "updated data/breadth-extra.json, then redeploy the site.")


if __name__ == "__main__":
    main()
