#!/usr/bin/env python3
"""
Rules-based "breaking out today" scanner over the same ~966-ticker global ETF universe as
fetch_global_etf_data.py (imports its TICKERS list directly, so there's one source of truth
for the universe). This is the simple, no-ML scanner from the ETF-ML-Screener project's
05_current_breakouts.py, ported to run daily in this repo's own GitHub Action instead of
locally -- NOT the trained ML breakout-probability model, which is a separate, heavier
project kept local for now.

The default flag (also the one used server-side for the "asof"-day snapshot) is:
    today's close is a new 20-day high  AND  today's volume >= 1.5x its trailing 20-day
    average volume

...but the lookback window (20/50/100/200 days) and the volume multiple are both adjustable
on the site itself, live, with no extra fetch -- each row also carries its own trimmed
close/volume history (last ~210 trading days, enough to cover a 200-day lookback with a
20-day volume-average tail), and the page recomputes the flag in JavaScript whenever the
person changes either control. The 52-week-high, RSI(14), and 50-day/200-day-SMA trend
columns are NOT adjustable (fixed-window indicators, shown for context) and stay
server-computed.

Writes data/breakout-scanner.json:
    {
      "asof": "YYYY-MM-DD",
      "rows": [
        {"t": "SPY", "price": 512.34, "chg1d": 0.42, "high20": true, "high52w": false,
         "volRatio": 1.87, "rsi14": 68.2, "aboveSma50": true, "aboveSma200": true,
         "breakout": true, "closes": [...], "vols": [...]},
        ...
      ]
    }
"closes"/"vols" are the trailing ~210 daily values (oldest to newest, same length, last
entry = today) used to recompute high20/high50/high100/high200 and the volume ratio
client-side for any lookback the person picks. Tickers with too little history to compute a
given metric report null for it rather than being dropped from the universe entirely (e.g. a
recently-listed ETF can still get a 20-day-high flag even without 252 days for a
52-week-high flag, and the client-side recompute falls back to "--" for a lookback longer
than the ticker's available history).

Run locally with:  python3 scripts/fetch_breakout_scanner.py
Runs automatically via .github/workflows/update-data.yml (as its own parallel job). Needs
curl_cffi installed (pip install curl_cffi) -- see the note above OUT_PATH for why.
"""
import json
import os
import random
import time

import yfinance as yf
import pandas as pd

from fetch_global_etf_data import TICKERS

OUT_PATH = "data/breakout-scanner.json"
LOOKBACK = "1y"   # ~252 trading days -- enough for the 52-week-high check and both SMAs.
# --- Why this fetch is structured the way it is ---
# The very first version of this script (single yf.download() call per batch of 30
# tickers) got the FIRST batch through fine and then came back completely empty for every
# batch after that, every run, no matter how much the inter-batch sleep/backoff was
# increased. That pattern -- works once, then hard-blocked regardless of pacing -- points to
# Yahoo Finance's bot detection fingerprinting the plain requests/urllib3 TLS handshake that
# yfinance uses by default (well documented as an issue specifically on cloud/datacenter IPs
# like GitHub Actions runners), not simple request-rate throttling. Slowing down a blocked
# client doesn't unblock it.
#
# The fix is to route requests through curl_cffi, which impersonates a real Chrome TLS
# fingerprint so Yahoo's bot detection doesn't flag the traffic in the first place. Combined
# with that: per-ticker fetches (not multi-ticker batch downloads, so one bad/delisted ticker
# can't take down a whole batch's worth of others), a short pause between tickers, and --
# still kept as a second line of defense -- exponential backoff plus merging into the
# previously-committed data/breakout-scanner.json instead of overwriting it, so a run that still hits
# trouble partway through keeps everything a prior successful run already fetched (same
# pattern as fetch_global_etf_data.py's load_existing()/merge_series()).
RETRIES = 4
SLEEP_BETWEEN_TICKERS = 1.2
SLEEP_ON_RETRY = 6.0             # base for exponential backoff: 6 * 2**attempt + jitter
SAVE_EVERY = 25                  # write progress to disk every N tickers processed

try:
    from curl_cffi import requests as cffi_requests
    _SESSION = cffi_requests.Session(impersonate="chrome")
except ImportError:
    print("WARNING: curl_cffi not installed -- falling back to yfinance's default session, "
          "which is the thing that was getting blocked. Add curl_cffi to the workflow's "
          "'pip install' step.")
    _SESSION = None

HIGH20_WINDOW = 20
HIGH52W_WINDOW = 252
VOL_AVG_WINDOW = 20
RSI_WINDOW = 14
SMA_SHORT = 50
SMA_LONG = 200
VOL_RATIO_BREAKOUT_MIN = 1.5
# Longest lookback the site's controls offer is 200 days; a 200-day volume average also
# needs 200 prior days, so 210 gives a small comfortable margin without shipping the full
# ~252-day fetch window (which would ~20% inflate the JSON for no benefit -- the fixed-window
# 52-week-high/SMA200 columns are computed here, server-side, from the full fetch instead).
CLIENT_HISTORY_WINDOW = 210


def compute_rsi(closes, window=RSI_WINDOW):
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window, min_periods=window).mean()
    avg_loss = loss.rolling(window, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def score_ticker(t, df):
    df = df.dropna(subset=["Close"])
    if len(df) < HIGH20_WINDOW + 1:
        return None
    closes = df["Close"]
    vols = df["Volume"].fillna(0) if "Volume" in df else pd.Series([0] * len(df), index=df.index)

    price = round(float(closes.iloc[-1]), 4)
    prev = float(closes.iloc[-2])
    chg1d = round((price - prev) / prev * 100, 2) if prev else None

    high20 = bool(closes.iloc[-1] >= closes.iloc[-HIGH20_WINDOW:].max())
    high52w = bool(closes.iloc[-1] >= closes.iloc[-HIGH52W_WINDOW:].max()) if len(closes) >= HIGH52W_WINDOW else None

    vol_ratio = None
    if len(vols) >= VOL_AVG_WINDOW + 1:
        avg_vol = float(vols.iloc[-(VOL_AVG_WINDOW + 1):-1].mean())  # trailing 20 days, excluding today
        today_vol = float(vols.iloc[-1])
        if avg_vol > 0:
            vol_ratio = round(today_vol / avg_vol, 2)

    rsi_series = compute_rsi(closes)
    rsi14 = round(float(rsi_series.iloc[-1]), 1) if pd.notna(rsi_series.iloc[-1]) else None

    above_sma50 = None
    if len(closes) >= SMA_SHORT:
        sma50 = float(closes.rolling(SMA_SHORT, min_periods=SMA_SHORT).mean().iloc[-1])
        above_sma50 = bool(price > sma50)
    above_sma200 = None
    if len(closes) >= SMA_LONG:
        sma200 = float(closes.rolling(SMA_LONG, min_periods=SMA_LONG).mean().iloc[-1])
        above_sma200 = bool(price > sma200)

    breakout = bool(high20 and vol_ratio is not None and vol_ratio >= VOL_RATIO_BREAKOUT_MIN)

    tail_closes = closes.iloc[-CLIENT_HISTORY_WINDOW:]
    tail_vols = vols.reindex(tail_closes.index).fillna(0)

    return {
        "t": t, "price": price, "chg1d": chg1d,
        "high20": high20, "high52w": high52w, "volRatio": vol_ratio, "rsi14": rsi14,
        "aboveSma50": above_sma50, "aboveSma200": above_sma200, "breakout": breakout,
        "closes": [round(float(c), 4) for c in tail_closes],
        "vols": [int(v) for v in tail_vols],
    }


def load_existing():
    """The previously committed data/breakout-scanner.json, if any -- keyed by ticker so this run
    can merge on top of it instead of starting from scratch (see the note above OUT_PATH)."""
    if not os.path.exists(OUT_PATH):
        return {}
    try:
        with open(OUT_PATH) as f:
            data = json.load(f)
        return {row["t"]: row for row in data.get("rows", []) if "t" in row}
    except Exception:
        return {}


def fetch_one(t):
    for attempt in range(RETRIES):
        try:
            tk = yf.Ticker(t, session=_SESSION)
            df = tk.history(period=LOOKBACK, interval="1d", auto_adjust=True)
            if df is not None and len(df) > 0:
                return df
        except Exception as e:
            print(f"  {t}: attempt {attempt+1} failed: {e}")
        sleep_s = SLEEP_ON_RETRY * (2 ** attempt) + random.uniform(0, 2)
        time.sleep(sleep_s)
    return None


def main():
    existing = load_existing()
    rows_by_ticker = dict(existing)   # start from the last good run, not from scratch
    n = len(TICKERS)
    got_this_run = 0
    for i, t in enumerate(TICKERS, start=1):
        df = fetch_one(t)
        if df is not None:
            scored = score_ticker(t, df)
            if scored:
                rows_by_ticker[t] = scored
                got_this_run += 1
        else:
            print(f"  {t}: no data after {RETRIES} attempts -- keeping prior data for it if any")

        if i % SAVE_EVERY == 0 or i == n:
            rows = list(rows_by_ticker.values())
            flagged = sum(1 for r in rows if r["breakout"])
            print(f"{i}/{n} processed ({got_this_run} fetched this run, {len(rows_by_ticker)} unique tickers total, {flagged} flagged)")
            with open(OUT_PATH, "w") as f:
                json.dump({"asof": time.strftime("%Y-%m-%d"), "rows": rows}, f, separators=(",", ":"))

        time.sleep(SLEEP_BETWEEN_TICKERS)

    rows = list(rows_by_ticker.values())
    flagged = sum(1 for r in rows if r["breakout"])
    print(f"Wrote data/breakout-scanner.json: {len(rows)}/{n} ETF tickers scored ({got_this_run} fetched this run), {flagged} flagged as breaking out.")


if __name__ == "__main__":
    main()
