# NIFTY 500 Bullish Momentum Scanner — Trade Plan
Adds BUY/WAIT calls, support, resistance, strong resistance, ATR-based stop loss, Target 1/2, volume ratio and R:R to the existing scanner.

## Trade plan
- Support/resistance: recent pivot levels plus EMA20 dynamic support.
- Stop loss: support/ATR based with a risk floor.
- Target 1: next resistance where available.
- Target 2: next strong resistance, otherwise risk/ATR extension.
- Volume: relative volume is confirmation; breakout BUY requires stronger volume.
- BUY is withheld when reward/risk is insufficient.

## Run
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```
