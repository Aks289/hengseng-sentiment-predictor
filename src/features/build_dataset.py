"""Merge all raw sources into data/processed/posts.csv"""
import glob
import json
from pathlib import Path

import pandas as pd
import yaml

RAW = Path("data/raw")
OUT = Path("data/processed/posts.csv")
COLS = ["exchange", "ticker", "source", "timestamp_utc", "text", "likes", "replies", "views", "url"]


def latest_files(pattern):
    """Keep only the newest file per (exchange, source, label)."""
    best = {}
    for f in sorted(glob.glob(str(RAW / pattern))):
        key = "_".join(Path(f).stem.split("_")[:-1])
        best[key] = f
    return list(best.values())


def first(item, keys):
    for k in keys:
        if item.get(k) not in (None, ""):
            return item[k]
    return None


def match_tickers(text, info):
    low = (text or "").lower()
    hits = []
    for t, name in info["tickers"].items():
        terms = [name, t.split(".")[0]] + info.get("aliases", {}).get(t, [])
        if any(term and term.lower() in low for term in terms):
            hits.append(t)
    return hits


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    rows = []

    for exchange, info in cfg["exchanges"].items():
        # LIHKG (label in file name = ticker)
        for f in latest_files(f"{exchange}_lihkg_*.json"):
            ticker = Path(f).stem.split("_")[2]
            for it in json.load(open(f, encoding="utf-8"))["items"]:
                text = " ".join(filter(None, [it.get("title"), it.get("own_text")]))
                rows.append([exchange, ticker, "lihkg", it.get("created_at"), text,
                             it.get("like_count"), it.get("reply_count"), None, it.get("thread_url")])

        # Telegram (no ticker in the feed, so match by name/alias)
        for f in latest_files(f"{exchange}_telegram_*.json"):
            for it in json.load(open(f, encoding="utf-8"))["items"]:
                for t in match_tickers(it.get("text"), info):
                    rows.append([exchange, t, "telegram", it.get("timestamp_utc"), it.get("text"),
                                 None, None, it.get("views"), f"https://t.me/{it.get('post_id')}"])

                       # Naver discussion (fields: writtenAt, title, text, views, likes, url)
        for f in latest_files(f"{exchange}_naver_board_*.json"):
            parts = Path(f).stem.split("_")
            ticker = parts[3] if len(parts) > 3 else None
            for it in json.load(open(f, encoding="utf-8"))["items"]:
                text = " ".join(filter(None, [it.get("title"), it.get("text")]))
                rows.append([exchange, ticker, "naver_board", it.get("writtenAt"), text,
                             it.get("likes"), None, it.get("views"), it.get("url")])
    # Exa news
    news_path = Path("data/processed/news.csv")
    if news_path.exists():
        for r in pd.read_csv(news_path).itertuples():
            text = " ".join(filter(None, [str(r.title), str(r.text) if pd.notna(r.text) else ""]))
            rows.append([r.exchange, r.ticker, "exa_news", r.published_utc, text, None, None, None, r.url])

    df = pd.DataFrame(rows, columns=COLS)
    df["timestamp_utc"] = df["timestamp_utc"].apply(lambda x: pd.to_datetime(x, utc=True, errors="coerce"))
    df = df.dropna(subset=["text", "ticker"])
    df = df[df["text"].str.strip() != ""].drop_duplicates(subset=["ticker", "source", "url", "text"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(df.groupby(["exchange", "source"]).size())
    print(f"Saved -> {OUT} ({len(df)} rows)")


if __name__ == "__main__":
    main()