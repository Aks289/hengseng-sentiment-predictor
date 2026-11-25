"""Download daily price bars for all configured tickers via yfinance."""
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

CONFIG_PATH = Path("config.yaml")
OUT_PATH = Path("data/processed/prices_daily.csv")


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_daily(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Daily OHLCV. Longer history than the 10-day social window,
    so the price model has enough rows to train on."""
    df = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
    if df.empty:
        return df
    df = df.reset_index()
    # 'date' = local exchange trading date; 'timestamp_utc' = same bar in UTC
    df["date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.date
    df["timestamp_utc"] = pd.to_datetime(df["Date"], utc=True)
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                            "Close": "close", "Volume": "volume"})
    return df[["date", "timestamp_utc", "open", "high", "low", "close", "volume"]]


def main() -> None:
    cfg = load_config()
    frames = []
    for exchange, info in cfg["exchanges"].items():
        for ticker, name in info["tickers"].items():
            df = fetch_daily(ticker)
            if df.empty:
                print(f"[warn] no data for {ticker}")
                continue
            df.insert(0, "asset_name", name)
            df.insert(0, "ticker", ticker)
            df.insert(0, "exchange", exchange)
            frames.append(df)
            print(f"{exchange} {ticker:<10} {name:<22} rows={len(df)} last_close={df['close'].iloc[-1]:.2f}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_csv(OUT_PATH, index=False)
    print(f"Saved -> {OUT_PATH}")


if __name__ == "__main__":
    main()