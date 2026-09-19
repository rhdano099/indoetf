#!/usr/bin/env python3
"""
Refreshes everything on the site except the ETF heatmaps (that's fetch_etf_data.py and
fetch_global_etf_data.py):
  - data/live.json                    sector indices, macro dashboard, FII/DII flows
  - data/nifty500-price.json          ^CRSLDX (Nifty 500 index) daily close
  - data/breadth-history.json         % of Nifty 500 constituents above their 200-day SMA
  - data/niftysc250-price.json        NIFTYSMLCAP250.NS (Nifty Smallcap 250 index) daily close
  - data/breadth-history-sc250.json   % of Nifty Smallcap 250 constituents above their 200-day SMA

Every step is wrapped so one failing source never wipes out data that's already good —
each section only gets overwritten if its own fetch succeeds. No API key anywhere:
yfinance reads Yahoo Finance's public endpoints, and the FII/DII pull tries NSE's public
JSON API with a plain browser User-Agent (best-effort — NSE sometimes blocks datacenter
IPs like GitHub Actions runners; if it fails, the flows table just keeps its last value).

Run locally with:  python3 scripts/fetch_live_data.py
Runs automatically via .github/workflows/update-data.yml on a daily schedule.
"""
import json
import time
import datetime
import urllib.request

import yfinance as yf

LIVE_PATH = "data/live.json"
NIFTY_PATH = "data/nifty500-price.json"
BREADTH_PATH = "data/breadth-history.json"
CONSTITUENTS_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"

SC250_INDEX_TICKER = "NIFTYSMLCAP250.NS"
SC250_NIFTY_PATH = "data/niftysc250-price.json"
SC250_BREADTH_PATH = "data/breadth-history-sc250.json"
SC250_CONSTITUENTS_URL = "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv"

SECTOR_TICKERS = [
    ("FMCG", "^CNXFMCG"),
    ("PSU Bank", "^CNXPSUBANK"),
    ("Realty", "^CNXREALTY"),
    ("Bank", "^NSEBANK"),
    ("Pvt Bank", "NIFTY_PVT_BANK.NS"),
    ("Media", "^CNXMEDIA"),
    ("Fin Service", "^CNXFIN"),
    ("Oil & Gas", "NIFTY_OIL_AND_GAS.NS"),
    ("Metal", "^CNXMETAL"),
    ("Auto", "^CNXAUTO"),
    ("Consr Durbl", "NIFTY_CONSR_DURBL.NS"),
    ("Healthcare", "NIFTY_HEALTHCARE.NS"),
    ("Pharma", "^CNXPHARMA"),
    # "Midsml Health" has no Yahoo Finance ticker — left out, keeps its last static value.
    ("IT", "^CNXIT"),
]


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))


def pct_change_1d(ticker):
    h = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=True)
    if len(h) < 2:
        return None
    last, prev = float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])
    return round((last - prev) / prev * 100, 2)


def fetch_sectors(existing_sectors):
    by_name = {s["n"]: s for s in existing_sectors}
    for name, ticker in SECTOR_TICKERS:
        try:
            chg = pct_change_1d(ticker)
            if chg is not None:
                by_name[name] = {"n": name, "c": chg}
                print(f"  sector {name}: {chg}%")
        except Exception as e:
            print(f"  sector {name} FAILED: {e}")
        time.sleep(0.3)
    return list(by_name.values())


def fetch_macro(existing_macro):
    m = dict(existing_macro)
    try:
        h = yf.Ticker("^INDIAVIX").history(period="5d", interval="1d")
        if len(h) >= 2:
            last, prev = float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])
            m["vix"] = {"v": round(last, 2), "chg": round((last - prev) / prev * 100, 2),
                        "asof": datetime.date.today().strftime("%d %b %Y")}
    except Exception as e:
        print(f"  vix FAILED: {e}")
    try:
        h = yf.Ticker("INR=X").history(period="5d", interval="1d")
        if len(h) >= 1:
            m["usdinr"] = {"v": round(float(h["Close"].iloc[-1]), 2),
                           "asof": datetime.date.today().strftime("%d %b %Y")}
    except Exception as e:
        print(f"  usdinr FAILED: {e}")
    try:
        h = yf.Ticker("BZ=F").history(period="5d", interval="1d")
        if len(h) >= 2:
            last, prev = float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])
            prevm = m.get("brent", {})
            m["brent"] = {"v": round(last, 2), "chg": round(last - prev, 2),
                          "ychg_pct": prevm.get("ychg_pct", 0),
                          "asof": datetime.date.today().strftime("%d %b %Y")}
    except Exception as e:
        print(f"  brent FAILED: {e}")
    # Nifty 50 forward PE and the 10Y G-Sec yield have no free live feed — left untouched.
    return m


def fetch_flows(existing_flows):
    # Best-effort: NSE's own provisional FII/DII JSON. Frequently blocked from datacenter
    # IPs (including GitHub Actions runners) — on any failure, keep last week's figures.
    try:
        req = urllib.request.Request(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "application/json",
                "Referer": "https://www.nseindia.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        rows = []
        for row in data:
            d = datetime.datetime.strptime(row["date"], "%d-%b-%Y").strftime("%d %b")
            rows.append({"d": d, "fii": float(row["fiiBuyValue"]) - float(row["fiiSellValue"]),
                         "dii": float(row["diiBuyValue"]) - float(row["diiSellValue"])})
        if rows:
            print(f"  flows: {len(rows)} rows from NSE")
            return rows[-7:]
    except Exception as e:
        print(f"  flows FAILED (keeping last known week): {e}")
    return existing_flows


def fetch_index_price(ticker, existing, label):
    # yf.Ticker(...).history(period="max") has repeatedly come back badly stale for these
    # NSE index symbols (^CRSLDX capped out around 2015, NIFTYSMLCAP250.NS around 2014) —
    # a Yahoo/yfinance quirk specific to that code path for these tickers, not a real data
    # gap (the index itself trades every day). yf.download() against a shorter, explicit
    # period goes through a different Yahoo endpoint and reliably returns current data
    # instead, so that's used here, with the existing series only replaced when the new
    # pull is actually fresher (never regress to something staler than what's already saved).
    series = None
    for period in ("10y", "5y", "2y", "1y"):
        try:
            h = yf.download(ticker, period=period, interval="1d", auto_adjust=True,
                             threads=False, progress=False)
            if h is not None and len(h) > 0:
                closes = h["Close"]
                if hasattr(closes, "iloc") and closes.ndim > 1:
                    closes = closes.iloc[:, 0]
                series = [[d.strftime("%Y-%m-%d"), round(float(c), 2)] for d, c in closes.dropna().items()]
                if series:
                    break
        except Exception as e:
            print(f"  {label} price ({period}) FAILED: {e}")
    if not series:
        print(f"  {label} price: no data fetched, keeping existing ({len(existing)} rows)")
        return existing

    new_last = series[-1][0]
    old_last = existing[-1][0] if existing else None
    days_stale = (datetime.date.today() - datetime.datetime.strptime(new_last, "%Y-%m-%d").date()).days
    if days_stale > 10:
        print(f"  {label} price: fetched series is still stale (latest {new_last}, {days_stale}d old) — Yahoo may not have fresher data for this ticker right now")
    if old_last and old_last >= new_last:
        print(f"  {label} price: existing data ({old_last}) already as fresh or fresher than fetch ({new_last}), keeping existing")
        return existing
    print(f"  {label} price: {len(series)} rows, latest {new_last}")
    return series


def fetch_nifty500_price(existing):
    return fetch_index_price("^CRSLDX", existing, "nifty500")


def fetch_breadth_generic(constituents_url, existing, default_last_date, label, seed_period="300d", seed_threshold=200):
    # existing: [["YYYY-MM-DD", pct], ...] — only appends dates after the last saved one,
    # UNLESS existing is still "thin" (fewer than seed_threshold rows — i.e. an index with
    # no static backfill that's only had a run or two), in which case a longer seed_period
    # is fetched and used to REPLACE existing outright with a deeper history. Otherwise the
    # first run(s) only yield a tiny sliver of valid post-200-day-SMA-warmup days and every
    # "5Y"/"10Y"/"ALL" range on the chart looks identical (there's nothing more to show yet)
    # until months of daily incremental runs slowly accumulate more.
    reseeding = len(existing) < seed_threshold
    period = seed_period if reseeding else "300d"
    last_date = existing[-1][0] if existing else default_last_date
    try:
        req = urllib.request.Request(constituents_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode("utf-8-sig")
        import csv, io
        symbols = [row["Symbol"] for row in csv.DictReader(io.StringIO(text))]
        print(f"  {label} breadth: {len(symbols)} constituents")
    except Exception as e:
        print(f"  {label} breadth constituent list FAILED, skipping: {e}")
        return existing

    import pandas as pd
    tickers = [s + ".NS" for s in symbols]
    try:
        raw = yf.download(tickers, period=period, interval="1d", auto_adjust=True,
                           group_by="ticker", threads=True, progress=False)
    except Exception as e:
        print(f"  {label} breadth price download FAILED: {e}")
        return existing

    closes = {}
    for t in tickers:
        try:
            s = raw[t]["Close"].dropna()
            if len(s) >= 200:
                closes[t] = s
        except Exception:
            continue
    if not closes:
        print(f"  {label} breadth: no usable price series, skipping")
        return existing

    df = pd.DataFrame(closes).sort_index()
    sma200 = df.rolling(200, min_periods=200).mean()
    valid = df.notna() & sma200.notna()
    above = (df > sma200) & valid
    breadth_pct = (above.sum(axis=1) / valid.sum(axis=1).replace(0, pd.NA) * 100).dropna()

    if reseeding:
        all_rows = [[dt.strftime("%Y-%m-%d"), round(float(pct), 2)] for dt, pct in breadth_pct.items()]
        if len(all_rows) > len(existing):
            print(f"  {label} breadth: reseeding with deeper history ({len(all_rows)} rows vs {len(existing)} before)")
            return all_rows
        print(f"  {label} breadth: reseed fetch wasn't deeper than existing, keeping existing")
        return existing

    new_rows = []
    for dt, pct in breadth_pct.items():
        ds = dt.strftime("%Y-%m-%d")
        if ds > last_date:
            new_rows.append([ds, round(float(pct), 2)])
    if new_rows:
        print(f"  {label} breadth: appending {len(new_rows)} new day(s)")
        return existing + new_rows
    print(f"  {label} breadth: already up to date")
    return existing


def fetch_breadth(existing):
    return fetch_breadth_generic(CONSTITUENTS_URL, existing, "2006-10-20", "nifty500")


def main():
    live = load_json(LIVE_PATH, {"sectors": [], "macro": {}, "flows": []})
    live["sectors"] = fetch_sectors(live.get("sectors", []))
    live["macro"] = fetch_macro(live.get("macro", {}))
    live["flows"] = fetch_flows(live.get("flows", []))
    live["asof"] = datetime.datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")
    save_json(LIVE_PATH, live)

    nifty = load_json(NIFTY_PATH, [])
    nifty = fetch_nifty500_price(nifty)
    save_json(NIFTY_PATH, nifty)

    breadth = load_json(BREADTH_PATH, [])
    breadth = fetch_breadth(breadth)
    save_json(BREADTH_PATH, breadth)

    sc250_price = load_json(SC250_NIFTY_PATH, [])
    sc250_price = fetch_index_price(SC250_INDEX_TICKER, sc250_price, "sc250")
    save_json(SC250_NIFTY_PATH, sc250_price)

    sc250_breadth = load_json(SC250_BREADTH_PATH, [])
    sc250_breadth = fetch_breadth_generic(SC250_CONSTITUENTS_URL, sc250_breadth, "2024-01-01", "sc250", seed_period="3y")
    save_json(SC250_BREADTH_PATH, sc250_breadth)

    print("Done.")


if __name__ == "__main__":
    main()
