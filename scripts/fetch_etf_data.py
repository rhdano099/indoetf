#!/usr/bin/env python3
"""
Pulls daily close prices for the 98 NSE ETFs used in the Bhavcopy heatmap and writes
data/etf-history.json in the shape the heatmap's "Connect live data" loader expects:

    { "SYMBOL": [["YYYY-MM-DD", price], ...], ... }

Run locally with:  python3 scripts/fetch_etf_data.py
Runs automatically via .github/workflows/update-data.yml on a daily schedule.

No API key needed — yfinance reads Yahoo Finance's public endpoints.
"""
import json
import time
import yfinance as yf

# The 98 symbols from the NSE ETF master sheet (MW-ETF-17-Sep-2026.csv).
# yfinance needs the ".NS" suffix for NSE-listed tickers.
SYMBOLS = [
    "EQUAL200","HDFCBSE500","DIVIDEND","ICICIB22","ECAPINSURE","MOVALUE","MOHEALTH",
    "GROWWHOSPI","DEFENCE","MOINFRA","INSUREIETF","ELMDIV","MOMMIDCAP","MIDSELIETF",
    "MIDBANKADD","GROWWPOWER","SBIBPB","MOQUALITY","SELECTIPO","HDFCSENSEX","SNXT30BEES",
    "SNXT50BETA","BANK10BETF","MSCI360","TOP100CASE","NIFTY100EW","ESG","LOWVOLIETF",
    "HDFCQUAL","GROWWN200","ALPHAETF","MOM30IETF","NIFTYQLITY","VAL30IETF","NIFTYBEES",
    "SBINEQWETF","SHARIABEES","NV20IETF","MONIFTY500","FLEXIADD","HEALTHCARE","GROWWLOVOL",
    "MOMENTUM50","MULTICAP","EMULTIMQ","VALUEAXIS","ALPHA","ALPL30IETF","AUTOIETF",
    "BANKIETF","MOCAPITAL","CEMNTGROWW","CHEMICAL","COMMOIETF","CPSEETF","DIVOPPBEES",
    "ENERGY","GROWWEV","BFSI","FINIETF","FMCGIETF","FMCGADD","HDFCGROWTH","HEALTHY",
    "CONSUMBEES","MODEFENCE","INFRA","GROWWNET","MAKEINDIA","CONSUMER","GROWWRAIL",
    "MOTOUR","INFRAIETF","ITBEES","ELM250","METALIETF","MIDCAPETF","MOMIDMTM","MIDQ50ADD",
    "MIDCAP","MIDSMALL","MNC","NEXT50IETF","OILIETF","PHARMABEES","PVTBANIETF","ABSLPSE",
    "PSUBNKBEES","MOREALTY","MOSERVICE","HDFCSML250","SMALLCAP","SML100CASE","TOP10ADD",
    "TOP15IETF","TOP20","AONETOTAL","AONETMMQ50",
]

OUT_PATH = "data/etf-history.json"
LOOKBACK = "2y"     # how much history to keep in the JSON (trim to taste)
RETRIES = 4
SLEEP_BETWEEN = 1.0   # seconds between tickers, be polite to Yahoo's endpoint
SLEEP_ON_RETRY = 8.0  # backs off further each retry — a flat 1.5s wasn't enough once Yahoo
                       # started rate-limiting (this job now runs alongside two other fetch
                       # jobs in parallel, all hitting Yahoo from GitHub's runner IP range)


def fetch_one(ticker):
    for attempt in range(RETRIES):
        try:
            h = yf.Ticker(ticker + ".NS").history(period=LOOKBACK, interval="1d", auto_adjust=True)
            if len(h) > 0:
                series = [[d.strftime("%Y-%m-%d"), round(float(c), 4)] for d, c in h["Close"].items() if c == c]
                if series:
                    return series
        except Exception as e:
            print(f"  {ticker}: attempt {attempt+1} failed ({e})")
        time.sleep(SLEEP_ON_RETRY * (attempt + 1))
    return None


def main():
    result = {}
    missing = []
    for i, sym in enumerate(SYMBOLS, 1):
        print(f"[{i}/{len(SYMBOLS)}] {sym} ...", end=" ")
        series = fetch_one(sym)
        if series:
            result[sym] = series
            print(f"{len(series)} rows")
        else:
            missing.append(sym)
            print("FAILED")
        # Save progress after every symbol so a run that gets cut off partway (timeout,
        # rate-limit) still keeps whatever it fetched instead of losing the whole thing.
        with open(OUT_PATH, "w") as f:
            json.dump(result, f, separators=(",", ":"))
        time.sleep(SLEEP_BETWEEN)

    print(f"\nWrote {OUT_PATH}: {len(result)}/{len(SYMBOLS)} symbols.")
    if missing:
        print(f"Missing ({len(missing)}): {missing}")


if __name__ == "__main__":
    main()
