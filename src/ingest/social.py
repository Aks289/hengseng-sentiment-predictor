"""Run the Apify actors configured in config.yaml and save raw JSON.

Usage:
    python -m src.ingest.social --test   # 1 ticker per exchange (cheap)
    python -m src.ingest.social          # full run
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()
RAW_DIR = Path("data/raw")


def fill(obj, values):

    if obj == "{aliases}":
        return values["aliases"]
    if isinstance(obj, str):
        return obj.format(**values)
    if isinstance(obj, list):
        return [fill(x, values) for x in obj]
    if isinstance(obj, dict):
        return {k: fill(v, values) for k, v in obj.items()}
    return obj


def run_actor(client, actor_id, run_input):
    run = client.actor(actor_id).call(run_input=run_input)
    items = list(client.dataset(run.default_dataset_id).iterate_items())
    return run.id, items


def save(exchange, source, label, run_id, items):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RAW_DIR / f"{exchange}_{source}_{label}_{stamp}.json"
    payload = {"run_id": run_id, "fetched_utc": stamp, "count": len(items), "items": items}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  saved {len(items):>4} items -> {path.name}")


def main():
    test = "--test" in sys.argv
    token = os.getenv("APIFY_TOKEN").strip()
    if not token:
        sys.exit("APIFY_TOKEN is not set")
    client = ApifyClient(token)
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))

    for exchange, info in cfg["exchanges"].items():
        tickers = list(info["tickers"].items())
        if test:
            tickers = tickers[:1]
        for source, scfg in info.get("sources", {}).items():
            if not scfg.get("enabled", True):
                print(f"[{exchange}] {source}: skipped (disabled)")
                continue
            print(f"[{exchange}] {source} ({scfg['actor_id']})")
            if scfg.get("per_ticker", True):
                for ticker, name in tickers:
                    values = {
                        "ticker": ticker,
                        "code": ticker.split(".")[0],
                        "name": name,
                        "aliases": info.get("aliases", {}).get(ticker, [name]),
                    }
                    try:
                        run_id, items = run_actor(client, scfg["actor_id"], fill(scfg["input"], values))
                        save(exchange, source, ticker, run_id, items)
                    except Exception as e:
                        print(f"  [warn] {ticker}: {e}")
            else:
                try:
                    run_id, items = run_actor(client, scfg["actor_id"], scfg["input"])
                    save(exchange, source, "all", run_id, items)
                except Exception as e:
                    print(f"  [warn] {source}: {e}")


if __name__ == "__main__":
    main()