# NIFTY 500 Bullish Momentum Scanner

## Strategy
- Close > EMA20
- EMA20 > EMA50
- MACD Line > 0
- MACD Histogram > 0
- RSI(14) > 55 and < 70
- Stochastic(14,3,3) > 40 and < 75
- Volume > SMA(Volume,20)

## Universe
NIFTY 500 symbols are downloaded automatically. The app tries the NSE list first and then uses a fallback mirror.

Market data and market capitalization are obtained from Yahoo Finance through `yfinance`.

## Timeframes
Dashboard filters:
- 15 Min
- 1 Hour
- 1 Day

You can select ANY or ALL selected timeframes.

## Market cap
Default minimum market cap is ₹10,000 Crore.

## Run locally
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy on Streamlit Community Cloud
1. Create a GitHub repository.
2. Upload all files from this ZIP.
3. Commit to `main`.
4. Go to Streamlit Community Cloud and create a new app.
5. Select your GitHub repository.
6. Set entrypoint to `streamlit_app.py`.
7. Deploy.

## Important
Free Streamlit Community Cloud storage is not suitable as a permanent database. This app automatically refreshes the live universe/data using cache TTL and the Refresh button. If you later want a permanent historical database, add PostgreSQL, Supabase, or another external database.
