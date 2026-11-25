"""Scrape public Telegram channels via the t.me/s web preview (free, no login)."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup

RAW_DIR = Path("data/raw")
HEADERS = {"User-Agent": "Mozilla/5.0"}


def parse_views(text):
    if not text:
        return None
    text = text.strip().upper()
    m = re.match(r"([\d.]+)([KM]?)", text)
    if not m:
        return None
    n = float(m.group(1))
    return int(n * {"": 1, "K": 1_000, "M": 1_000_000}[m.group(2)])


def scrape_channel(channel, since, max_pages=10):
    rows, before = [], None
    for _ in range(max_pages):
        url = f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"  [warn] {channel}: HTTP {resp.status_code}")
            break
        msgs = BeautifulSoup(resp.text, "html.parser").select("div.tgme_widget_message")
        if not msgs:
            break
        oldest = None
        for m in msgs:
            text_el = m.select_one(".tgme_widget_message_text")
            time_el = m.select_one("time")
            views_el = m.select_one(".tgme_widget_message_views")
            ts = pd.to_datetime(time_el.get("datetime"), utc=True) if time_el else None
            if ts is not None and (oldest is None or ts < oldest):
                oldest = ts
            if ts is None or ts < since:
                continue
            rows.append({
                "channel": channel,
                "post_id": m.get("data-post"),
                "text": text_el.get_text(" ", strip=True) if text_el else None,
                "timestamp_utc": ts.isoformat(),
                "views": parse_views(views_el.get_text() if views_el else None),
            })
        if oldest is not None and oldest < since:
            break
        before = msgs[0].get("data-post").split("/")[-1]
    return rows


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    since = pd.Timestamp(datetime.now(timezone.utc) - timedelta(days=cfg["lookback_days"]))
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for exchange, info in cfg["exchanges"].items():
        items = []
        for ch in info.get("telegram_channels", []):
            if ch.startswith("PUT_"):
                print(f"[{exchange}] skipping placeholder {ch}")
                continue
            got = scrape_channel(ch, since)
            print(f"[{exchange}] {ch}: {len(got)} messages")
            items += got
        path = RAW_DIR / f"{exchange}_telegram_all_{stamp}.json"
        path.write_text(json.dumps({"fetched_utc": stamp, "count": len(items), "items": items},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  saved {len(items)} items -> {path.name}")


if __name__ == "__main__":
    main()