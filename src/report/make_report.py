"""Build reports/report.html: per-exchange ranking, sentiment, mentions, price + levels."""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

COL = {"bullish": "#2e7d32", "bearish": "#c62828", "neutral": "#757575"}
summ = pd.read_csv("data/processed/ticker_summary.csv")
posts = pd.read_csv("data/processed/posts_scored.csv")
daily = pd.read_csv("data/processed/sentiment_daily.csv", parse_dates=["local_date"])
prices = pd.read_csv("data/processed/prices_daily.csv", parse_dates=["date"])
pred_p, met_p = Path("data/processed/predictions.csv"), Path("data/processed/metrics.csv")

html = ["<html><head><meta charset='utf-8'><title>HengSeng Sentiment Report</title></head>"
        "<body style='font-family:sans-serif;max-width:1100px;margin:auto;padding:16px'>"
        "<h1>Social sentiment report</h1>"
        "<p>Tickers ranked by social mentions, then sentiment. Sentiment is a word-list baseline in [-1, 1]; "
        "position is inferred from sentiment plus the 20-day price trend.</p>"]

_first = [True]


def add(fig):
    # Load the Plotly library with the first chart only, so every chart can render
    html.append(fig.to_html(full_html=False, include_plotlyjs="cdn" if _first[0] else False))
    _first[0] = False


for ex, s in summ.groupby("exchange"):
    s = s.sort_values(["mentions", "sentiment_score"], ascending=False)
    html.append(f"<h2>{ex}</h2>")

    cols = ["ticker", "asset_name", "current_price", "mentions", "sources_used",
            "sentiment_score", "direction", "position", "support_20d", "resistance_20d"]
    add(go.Figure(go.Table(header=dict(values=cols, fill_color="#eceff1"),
                           cells=dict(values=[s[c] for c in cols]))).update_layout(height=330, margin=dict(t=10)))

    fig = make_subplots(rows=1, cols=2, subplot_titles=("Sentiment score and direction", "Mentions by source"))
    fig.add_trace(go.Bar(x=s["asset_name"], y=s["sentiment_score"],
                         marker_color=[COL[d] for d in s["direction"]], showlegend=False), row=1, col=1)
    mix = posts[posts["exchange"] == ex].groupby(["ticker", "source"]).size().reset_index(name="n")
    names = dict(zip(s["ticker"], s["asset_name"]))
    for src, g in mix.groupby("source"):
        fig.add_trace(go.Bar(x=[names.get(t, t) for t in g["ticker"]], y=g["n"], name=src), row=1, col=2)
    fig.update_layout(barmode="stack", height=380)
    add(fig)

    n = len(s)
    fig = make_subplots(rows=n, cols=1, specs=[[{"secondary_y": True}]] * n,
                        subplot_titles=[f"{r.asset_name} ({r.ticker})" for r in s.itertuples()])
    for i, r in enumerate(s.itertuples(), start=1):
        p = prices[prices["ticker"] == r.ticker].tail(30)
        d = daily[daily["ticker"] == r.ticker]
        fig.add_trace(go.Scatter(x=p["date"], y=p["close"], name="close", line=dict(color="#1565c0"),
                                 showlegend=(i == 1)), row=i, col=1, secondary_y=False)
        fig.add_trace(go.Bar(x=d["local_date"], y=d["sentiment"], name="daily sentiment", opacity=0.4,
                             marker_color="#ef6c00", showlegend=(i == 1)), row=i, col=1, secondary_y=True)
        fig.add_hline(y=r.support_20d, line_dash="dot", line_color="green", row=i, col=1)
        fig.add_hline(y=r.resistance_20d, line_dash="dot", line_color="red", row=i, col=1)
    fig.update_layout(height=260 * n, title="Price (30d) with 20-day support/resistance and daily sentiment")
    add(fig)

if pred_p.exists():
    pr = pd.read_csv(pred_p)
    html.append("<h2>n+1 price prediction (forecast for the next trading day after the date shown)</h2>")
    add(go.Figure(go.Table(header=dict(values=list(pr.columns), fill_color="#eceff1"),
                           cells=dict(values=[pr[c] for c in pr.columns]))).update_layout(height=420))
if met_p.exists():
    m = pd.read_csv(met_p)
    html.append("<h2>Walk-forward validation (last 15 trading days)</h2>")
    add(go.Figure(go.Table(header=dict(values=list(m.columns), fill_color="#eceff1"),
                           cells=dict(values=[m[c] for c in m.columns]))).update_layout(height=260))

html.append("<p><b>Limits:</b> about 10 days of social data; Naver posts cover only the latest day; "
            "LIHKG has no views, reposts or follower counts; sentiment is a keyword baseline, not a trained model; "
            "forecasts are illustrative, not trading signals.</p></body></html>")
Path("reports").mkdir(exist_ok=True)
Path("reports/report.html").write_text("\n".join(html), encoding="utf-8")
print("Saved -> reports/report.html")