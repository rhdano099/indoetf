#!/usr/bin/env python3
"""
Pulls daily close prices for the 98 NSE ETFs used in the Bhavcopy heatmap and writes
data/etf-history.json in the shape the heatmap's "Connect live data" loader expects:

    { "SYMBOL": [["YYYY-MM-DD", price], ...], ... }

Run locally with:  python3 scripts/fetch_etf_data.py
Runs automatically via .github/workflows/update-data.yml on a daily schedule.

No API key needed — yfinance reads Yahoo Finance's public endpoints.

Fetched with yf.download() in small batches, not one yf.Ticker(...).history() call per
symbol — every single-ticker Ticker.history() fetch in this project has ended up hitting
Yahoo's rate limit hard on GitHub's runner IPs (this same site's Nifty 500 index price,
Nifty Smallcap 250 index price, and the original version of this exact script all hit it),
while yf.download()'s batched endpoint has consistently held up. Small batches + no
threading + pauses between them is what keeps this reliable — see fetch_global_etf_data.py
for the same pattern.
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
BATCH_SIZE = 20
RETRIES = 4
SLEEP_BETWEEN_BATCHES = 2.5
SLEEP_ON_RETRY = 8.0


def fetch_batch(tickers):
    out = {}
    raw = None
    for attempt in range(RETRIES):
        try:
            raw = yf.download([t + ".NS" for t in tickers], period=LOOKBACK, interval="1d",
                               auto_adjust=True, group_by="ticker", threads=False, progress=False)
            if raw is not None and len(raw) > 0:
                break
        except Exception as e:
            print(f"  batch download attempt {attempt+1} failed: {e}")
            raw = None
        time.sleep(SLEEP_ON_RETRY * (attempt + 1))
    if raw is None or len(raw) == 0:
        return out
    single = len(tickers) == 1
    for t in tickers:
        try:
            s = raw["Close"] if single else raw[t + ".NS"]["Close"]
            s = s.dropna()
            if len(s) > 0:
                out[t] = [[d.strftime("%Y-%m-%d"), round(float(c), 4)] for d, c in s.items()]
        except Exception:
            continue
    return out


def main():
    result = {}
    missing = []
    n_batches = (len(SYMBOLS) - 1) // BATCH_SIZE + 1
    for i in range(0, len(SYMBOLS), BATCH_SIZE):
        batch = SYMBOLS[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        got = fetch_batch(batch)
        result.update(got)
        missing.extend([s for s in batch if s not in got])
        print(f"Batch {batch_num}/{n_batches}: got {len(got)}/{len(batch)} — running total {len(result)}")
        # Save progress after every batch so a run that gets cut off partway (timeout,
        # rate-limit) still keeps whatever it fetched instead of losing the whole thing.
        with open(OUT_PATH, "w") as f:
            json.dump(result, f, separators=(",", ":"))
        time.sleep(SLEEP_BETWEEN_BATCHES)

    print(f"\nWrote {OUT_PATH}: {len(result)}/{len(SYMBOLS)} symbols.")
    if missing:
        print(f"Missing ({len(missing)}): {missing}")


if __name__ == "__main__":
    main()
