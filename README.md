# HengSeng Sentiment Price Prediction

Python pipeline that collects social posts and news for 10 tickers (5 HKEX, 5 KRX), scores sentiment, builds a per-ticker report, and predicts the next-day (n+1) price with walk-forward validation.

Open `reports/report.html` for the visual report (download it and open it in a browser).

## Tickers
- **HKEX:** 0700.HK Tencent, 0005.HK HSBC Holdings, 9988.HK Alibaba, 3690.HK Meituan, 1810.HK Xiaomi
- **KRX:** 005930.KS Samsung Electronics, 000660.KS SK Hynix, 035420.KS Naver, 035720.KS Kakao, 005380.KS Hyundai Motor

## Sources
| Exchange | Social source 1 | Social source 2 | News |
|---|---|---|---|
| HKEX | LIHKG (Apify) | Telegram: `chinadagudong` | Exa |
| KRX | Naver stock discussion boards (Apify) | Telegram: `corevalue`, `financialnewssummary` | Exa |

**Apify actors (for reproduction):**
- `claude_code_reviewer/lihkg-scraper-en`: search mode, last 10 days, Chinese keyword aliases per ticker, 15 rows per keyword.
- `hgservices/naver-stock-discussion-scraper`: one run per Korean ticker, newest posts first, `maxResults: 50`, `dateFrom: 2026-11-15`.

**Other sources:**
- Telegram: collected from public channel preview pages (`t.me/s/<channel>`) with a small Python scraper (`src/ingest/telegram.py`), not an Apify actor. Posts are matched to tickers by company name, code and aliases (Chinese, Korean, English).
- Exa: 5 news articles per ticker for the last 10 days (`src/ingest/news.py`).
- Prices: yfinance daily bars, 6 months of history (`src/ingest/prices.py`).

Tickers, aliases, channels and actor inputs are all set in `config.yaml`.

## Setup
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then add APIFY_TOKEN and EXA_API_KEY
```
The keys can also be set as environment variables (for example Codespaces secrets). Strip any trailing spaces or line breaks from the values.

## Run order
```bash
python -m src.ingest.prices          # daily price bars (yfinance)
python -m src.ingest.social          # Apify actors enabled in config.yaml (LIHKG, Naver)
python -m src.ingest.telegram        # Telegram channel previews
python -m src.ingest.news            # Exa news
python -m src.features.build_dataset # merge all sources -> data/processed/posts.csv
python -m src.sentiment.score        # sentiment, per-ticker table, daily sentiment
python -m src.model.predict          # n+1 model, walk-forward metrics, forecasts
python -m src.report.make_report     # writes reports/report.html
```
Use `python -m src.ingest.social --test` for a cheap run on one ticker per exchange. Each source can be switched on or off with `enabled:` in `config.yaml`. Raw scraped files are saved to `data/raw/` (git-ignored); small samples are in `data/sample/`.

## Method
- **Alignment:** all post and news timestamps are converted to UTC, then assigned to the exchange's local trading date (Hong Kong or Seoul time) to line up with daily price bars.
- **Sentiment:** a multilingual (Chinese, Korean, English) keyword baseline giving a score in [-1, 1] per post. Posts are weighted by engagement (likes, replies, views where available) and averaged per ticker per day.
- **Per-ticker output** (`data/processed/ticker_summary.csv`): ticker, asset name, current price, mentions, number of sources, sentiment score, direction (bullish, bearish or neutral), inferred position, 20-day support and resistance, and pivot-point S1/R1 levels.
- **Position:** inferred, not read from posts. It is "long bias" when sentiment is above 0.1 and the price is above its 20-day average, "short bias" for the mirror case, and "flat / wait" otherwise.
- **Report:** per exchange, tickers ranked by mentions then sentiment, with a sentiment and direction chart, a mentions-by-source chart, 30-day price charts with support, resistance and daily sentiment, plus the forecast and validation tables.
- **n+1 model:** the target is the next-day return. Features are lagged returns, 5-day volatility and daily weighted sentiment (mention counts were excluded because a one-day spike distorted the forecast). Baselines are "tomorrow = today" and "always up". Models are ridge regression on price features and on price plus sentiment.
- **Validation:** walk-forward with an expanding window over the last 15 trading days. Each day is predicted using only earlier days, with no random splits.

## Results
Row counts after merging: HKEX: Exa news 25, LIHKG 19, Telegram 7. KRX: Exa news 25, Naver boards 250, Telegram 106 (432 rows in total).

| Model (n=150: 10 tickers x 15 test days) | MAPE % | RMSE (return, %) | Directional accuracy |
|---|---|---|---|
| Baseline: tomorrow = today | 2.990 | 3.949 | n/a |
| Baseline: always up | 2.993 | 3.951 | 35.3% |
| Ridge: price features only | 2.937 | 3.938 | 57.3% |
| Ridge: price + sentiment | 2.926 | 3.921 | 58.7% |

The price + sentiment model is the best of the four on all three measures, improving MAPE by about 2% over the naive baseline. The margin over price-only ridge is very small (0.011 MAPE points; the 1.3-point directional gain is 2 correct calls out of 150), so this should be read as suggestive, not as evidence of a real signal. Sentiment history covers only about 10 days, so for most of the training window the sentiment feature is zero. The test window was mostly down days (always-up hit only 35.3%; a constant "always down" rule would have scored up to about 65%), so directional accuracy should not be read as skill. The n+1 forecasts in `data/processed/predictions.csv` are illustrative, not trading signals. A longer sentiment history is needed to test the idea properly.

## Limitations
- Only about 10 days of social data, and a small sample per ticker (LIHKG returned 1 to 8 threads per ticker).
- LIHKG search returns thread titles, not post bodies, so sentiment there is scored on titles. Its date filter works on thread activity, so one thread created earlier (October) appears in the data: the data is "threads with activity in the last 10 days".
- Naver posts are all from one day (2026-11-25) because they were collected newest-first with a cap of 50 per stock. They add sentiment for the latest day, which cannot be validated because that day has no next-day price yet.
- LIHKG has no views, reposts or follower counts. Telegram gives views; Naver gives views, likes and dislikes. Fields a source does not provide are left empty, and author follower counts are not available from any of the three sources.
- The Telegram channels are mostly analyst and news channels, not retail chatter. The HKEX channel is a Korean-language channel on China and Hong Kong stocks, so matching relies on Korean aliases.
- Sentiment is a keyword baseline and misses sarcasm, slang and profanity. The position column is inferred, not read from posts.
- Next steps: a multilingual transformer or LLM for sentiment, longer social history, more HK sources (for example Futu/Moomoo), and proper tests of statistical significance.