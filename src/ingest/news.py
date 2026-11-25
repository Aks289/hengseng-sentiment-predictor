"""Fetch recent news per ticker via Exa and save to CSV."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml
from exa_py import Exa

OUT = Path("data/processed/news.csv")


def main():
    key = (os.environ.get("EXA_API_KEY") or "").strip()
    if not key:
        raise SystemExit("EXA_API_KEY is not set")
    exa = Exa(key)

    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    since = (datetime.now(timezone.utc) - timedelta(days=cfg["lookback_days"])).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = []
    for exchange, info in cfg["exchanges"].items():
        for ticker, name in info["tickers"].items():
            try:
                res = exa.search_and_contents(
                    f"{name} stock news",
                    num_results=5,
                    start_published_date=since,
                    text={"max_characters": 800},
                )
            except Exception as e:
                print(f"[warn] {ticker}: {e}")
                continue
            for r in res.results:
                rows.append({
                    "exchange": exchange,
                    "ticker": ticker,
                    "asset_name": name,
                    "title": r.title,
                    "url": r.url,
                    "published_utc": r.published_date,
                    "text": r.text,
                })
            print(f"{ticker}: {len(res.results)} articles")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"Saved -> {OUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()