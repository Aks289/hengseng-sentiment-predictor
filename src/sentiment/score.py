"""Score sentiment, then build ticker_summary.csv and sentiment_daily.csv"""
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

POS = ["升", "利好", "看好", "買入", "买入", "增持", "突破", "反彈", "反弹", "強勢", "强势", "新高", "超預期", "盈喜", "回購",
       "상승", "급등", "호재", "매수", "강세", "신고가", "돌파", "반등", "흑자",
       "surge", "rally", "beat", "upgrade", "bullish", "gain", "record", "growth", "strong", "buy"]
NEG = ["跌", "利空", "看淡", "沽", "賣出", "卖出", "減持", "减持", "破位", "暴跌", "弱勢", "弱势", "新低", "盈警", "低見", "套牢", "崩",
       "하락", "급락", "악재", "매도", "약세", "신저가", "손절", "적자", "폭락", "부진",
       "plunge", "drop", "fall", "miss", "downgrade", "bearish", "sell", "loss", "weak", "decline", "probe"]


def score(text):
    t = str(text).lower()
    p = sum(t.count(w) for w in POS)
    n = sum(t.count(w) for w in NEG)
    return 0.0 if p + n == 0 else (p - n) / (p + n)


def direction(s):
    return "bullish" if s > 0.1 else "bearish" if s < -0.1 else "neutral"


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    tz = {ex: info["timezone"] for ex, info in cfg["exchanges"].items()}
    posts = pd.read_csv("data/processed/posts.csv", parse_dates=["timestamp_utc"])
    prices = pd.read_csv("data/processed/prices_daily.csv")

    posts["sentiment"] = posts["text"].apply(score)
    eng = posts[["likes", "replies"]].fillna(0).sum(axis=1) + posts["views"].fillna(0) / 100
    posts["weight"] = 1 + np.log1p(eng)
    posts["local_date"] = [ts.tz_convert(tz[ex]).date() if pd.notna(ts) else None
                           for ts, ex in zip(posts["timestamp_utc"], posts["exchange"])]
    posts.to_csv("data/processed/posts_scored.csv", index=False)

    daily = (posts.groupby(["exchange", "ticker", "local_date"])
             .apply(lambda g: pd.Series({"mentions": len(g),
                                         "sentiment": np.average(g["sentiment"], weights=g["weight"])}),
                    include_groups=False).reset_index())
    daily.to_csv("data/processed/sentiment_daily.csv", index=False)

    rows = []
    for (ex, t), g in posts.groupby(["exchange", "ticker"]):
        s = float(np.average(g["sentiment"], weights=g["weight"]))
        p = prices[prices["ticker"] == t].sort_values("date")
        if p.empty:
            continue
        last = p.iloc[-1]
        w20 = p.tail(20)
        sma20 = w20["close"].mean()
        pivot = (last["high"] + last["low"] + last["close"]) / 3
        if s > 0.1 and last["close"] > sma20:
            pos = "long bias"
        elif s < -0.1 and last["close"] < sma20:
            pos = "short bias"
        else:
            pos = "flat / wait"
        rows.append({
            "exchange": ex, "ticker": t, "asset_name": last["asset_name"],
            "current_price": round(last["close"], 2),
            "mentions": len(g), "sources_used": g["source"].nunique(),
            "sentiment_score": round(s, 3), "direction": direction(s), "position": pos,
            "support_20d": round(w20["low"].min(), 2), "resistance_20d": round(w20["high"].max(), 2),
            "pivot": round(pivot, 2), "S1": round(2 * pivot - last["high"], 2), "R1": round(2 * pivot - last["low"], 2),
        })
    out = pd.DataFrame(rows).sort_values(["exchange", "mentions", "sentiment_score"], ascending=[True, False, False])
    out.to_csv("data/processed/ticker_summary.csv", index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()