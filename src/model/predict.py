"""Next-day (n+1) return/price prediction with walk-forward validation."""
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PRICE_F = ["ret_1", "ret_5", "vol_5"]
ALL_F = PRICE_F + ["sentiment"]
TEST_DAYS = 15


def build():
    p = pd.read_csv("data/processed/prices_daily.csv", parse_dates=["date"]).sort_values(["ticker", "date"])
    g = p.groupby("ticker")["close"]
    p["ret_1"] = g.pct_change() * 100
    p["ret_5"] = g.pct_change(5) * 100
    p["vol_5"] = p.groupby("ticker")["ret_1"].transform(lambda s: s.rolling(5).std())
    p["next_close"] = g.shift(-1)
    p["target"] = p["next_close"] / p["close"] * 100 - 100      # next-day return, %
    s = pd.read_csv("data/processed/sentiment_daily.csv", parse_dates=["local_date"])
    s = s.rename(columns={"local_date": "date"})[["ticker", "date", "mentions", "sentiment"]]
    p = p.merge(s, on=["ticker", "date"], how="left")
    p[["mentions", "sentiment"]] = p[["mentions", "sentiment"]].fillna(0)
    return p


def fit_predict(train, test, feats):
    m = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    m.fit(train[feats], train["target"])
    return m.predict(test[feats])


def main():
    p = build()
    data = p.dropna(subset=ALL_F)
    lab = data.dropna(subset=["target"])
    test_dates = sorted(lab["date"].unique())[-TEST_DAYS:]

    recs = []
    for d in test_dates:                      # expanding window: train only on days before d
        tr, te = lab[lab["date"] < d], lab[lab["date"] == d]
        recs.append(te.assign(model="baseline: tomorrow = today", pred_ret=0.0))
        recs.append(te.assign(model="baseline: always up", pred_ret=0.01))
        recs.append(te.assign(model="ridge: price only", pred_ret=fit_predict(tr, te, PRICE_F)))
        recs.append(te.assign(model="ridge: price + sentiment", pred_ret=fit_predict(tr, te, ALL_F)))
    wf = pd.concat(recs)
    wf["pred_close"] = wf["close"] * (1 + wf["pred_ret"] / 100)
    wf["pct_err"] = (wf["pred_close"] - wf["next_close"]).abs() / wf["next_close"] * 100
    wf["sq_err"] = (wf["pred_ret"] - wf["target"]) ** 2
    wf["dir_hit"] = np.sign(wf["pred_ret"]) == np.sign(wf["target"])
    wf[["date", "ticker", "model", "close", "pred_close", "next_close", "pred_ret", "target"]].to_csv(
        "data/processed/walkforward.csv", index=False)

    metrics = wf.groupby("model").agg(MAPE_pct=("pct_err", "mean"),
                                      RMSE_ret=("sq_err", lambda x: np.sqrt(x.mean())),
                                      directional_acc=("dir_hit", "mean"),
                                      n=("pct_err", "size")).round(4)
    metrics.loc["baseline: tomorrow = today", "directional_acc"] = np.nan   # no direction call
    metrics.to_csv("data/processed/metrics.csv")
    print(metrics.to_string())

    # n+1 forecast from the latest bar of each ticker
    latest = data.sort_values("date").groupby("ticker").tail(1)
    latest = latest[latest["target"].isna()].copy()
    latest["pred_ret_pct"] = fit_predict(lab, latest, ALL_F)
    latest["pred_next_close"] = latest["close"] * (1 + latest["pred_ret_pct"] / 100)
    out = latest[["exchange", "ticker", "asset_name", "date", "close", "pred_ret_pct", "pred_next_close"]]
    out.round(3).to_csv("data/processed/predictions.csv", index=False)
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()