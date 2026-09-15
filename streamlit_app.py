
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

st.set_page_config(page_title="NIFTY 500 Momentum Scanner", layout="wide")

OFFICIAL_NIFTY500_URL = "https://www.nseindia.com/content/indices/ind_nifty500list.csv"
FALLBACK_NIFTY500_URL = "https://raw.githubusercontent.com/ganeshbiyer/Nse_Historical_Data/main/nifty500_symbols.csv"

TIMEFRAME_MAP = {
    "15 Min": {"interval": "15m", "period": "60d"},
    "1 Hour": {"interval": "1h", "period": "730d"},
    "1 Day": {"interval": "1d", "period": "2y"},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "text/csv,text/plain,*/*",
}

@st.cache_data(ttl=24*60*60, show_spinner=False)
def get_nifty500_universe():
    """Download NIFTY 500 symbols. Official NSE first, fallback to GitHub mirror."""
    errors = []
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        s.get("https://www.nseindia.com", timeout=15)
        r = s.get(OFFICIAL_NIFTY500_URL, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        if "Symbol" in df.columns:
            symbols = df["Symbol"].dropna().astype(str).str.strip().tolist()
            return pd.DataFrame({"symbol": symbols, "source": "NSE official"})
    except Exception as e:
        errors.append(str(e))

    try:
        r = requests.get(FALLBACK_NIFTY500_URL, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        symbols = df[col].dropna().astype(str).str.strip().tolist()
        return pd.DataFrame({"symbol": symbols, "source": "fallback mirror"})
    except Exception as e:
        errors.append(str(e))
        raise RuntimeError("Could not download NIFTY 500 list. " + " | ".join(errors))

@st.cache_data(ttl=6*60*60, show_spinner=False)
def get_market_cap(symbol):
    ticker = yf.Ticker(symbol + ".NS")
    try:
        fi = ticker.fast_info
        cap = getattr(fi, "market_cap", None)
        if cap is None and isinstance(fi, dict):
            cap = fi.get("market_cap")
        if cap is not None and np.isfinite(float(cap)):
            return float(cap)
    except Exception:
        pass
    try:
        info = ticker.info
        cap = info.get("marketCap")
        return float(cap) if cap else np.nan
    except Exception:
        return np.nan

@st.cache_data(ttl=60*60, show_spinner=False)
def get_large_cap_universe(symbols, min_market_cap):
    out = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {ex.submit(get_market_cap, s): s for s in symbols}
        for i, fut in enumerate(as_completed(futures), 1):
            s = futures[fut]
            try:
                cap = fut.result()
                if pd.notna(cap) and cap >= min_market_cap:
                    out.append((s, cap))
            except Exception:
                pass
    df = pd.DataFrame(out, columns=["symbol", "market_cap"])
    return df.sort_values("market_cap", ascending=False).reset_index(drop=True)

def ema(s, span):
    return s.ewm(span=span, adjust=False).mean()

def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def stochastic(high, low, close, k_period=14, k_smooth=3, d_period=3):
    lowest = low.rolling(k_period).min()
    highest = high.rolling(k_period).max()
    raw_k = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    k = raw_k.rolling(k_smooth).mean()
    d = k.rolling(d_period).mean()
    return k, d

def indicators(df):
    df = df.copy().dropna()
    if len(df) < 60:
        return None
    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    vol = df["Volume"].astype(float)

    df["EMA20"] = ema(close, 20)
    df["EMA50"] = ema(close, 50)
    macd_line = ema(close, 12) - ema(close, 26)
    signal = ema(macd_line, 9)
    df["MACD"] = macd_line
    df["MACD_HIST"] = macd_line - signal
    df["RSI14"] = rsi(close, 14)
    df["STOCH_K"], df["STOCH_D"] = stochastic(high, low, close, 14, 3, 3)
    df["VOL_SMA20"] = vol.rolling(20).mean()
    return df

def evaluate(df):
    x = df.iloc[-1]
    checks = {
        "Close > EMA20": x["Close"] > x["EMA20"],
        "EMA20 > EMA50": x["EMA20"] > x["EMA50"],
        "MACD > 0": x["MACD"] > 0,
        "MACD Histogram > 0": x["MACD_HIST"] > 0,
        "RSI 55-70": 55 < x["RSI14"] < 70,
        "Stochastic 40-75": 40 < x["STOCH_K"] < 75,
        "Volume > SMA20": x["Volume"] > x["VOL_SMA20"],
    }
    score = sum(bool(v) for v in checks.values())
    return checks, score, x

@st.cache_data(ttl=15*60, show_spinner=False)
def analyze_symbol(symbol, timeframe):
    cfg = TIMEFRAME_MAP[timeframe]
    try:
        df = yf.download(
            symbol + ".NS",
            period=cfg["period"],
            interval=cfg["interval"],
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        need = ["Open", "High", "Low", "Close", "Volume"]
        if not all(c in df.columns for c in need):
            return None
        ind = indicators(df[need])
        if ind is None:
            return None
        checks, score, x = evaluate(ind)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "match": all(checks.values()),
            "score": score,
            "close": float(x["Close"]),
            "EMA20": float(x["EMA20"]),
            "EMA50": float(x["EMA50"]),
            "MACD": float(x["MACD"]),
            "MACD_HIST": float(x["MACD_HIST"]),
            "RSI14": float(x["RSI14"]),
            "STOCH_K": float(x["STOCH_K"]),
            "volume": float(x["Volume"]),
            "vol_sma20": float(x["VOL_SMA20"]),
            "checks": checks,
            "as_of": str(ind.index[-1]),
        }
    except Exception:
        return None

def scan(universe, timeframes, match_mode, progress_cb):
    rows = []
    tasks = [(s, tf) for s in universe["symbol"].tolist() for tf in timeframes]
    total = len(tasks)
    done = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(analyze_symbol, s, tf): (s, tf) for s, tf in tasks}
        for fut in as_completed(futures):
            done += 1
            progress_cb(done / total, f"Analyzed {done}/{total} symbol-timeframe combinations")
            result = fut.result()
            if result:
                rows.append(result)

    if not rows:
        return pd.DataFrame(), pd.DataFrame()

    all_df = pd.DataFrame(rows)
    cap_map = universe.set_index("symbol")["market_cap"].to_dict()
    all_df["market_cap"] = all_df["symbol"].map(cap_map)

    if match_mode == "ALL selected timeframes":
        pivot = all_df.pivot_table(index="symbol", columns="timeframe", values="match", aggfunc="first").fillna(False)
        good_symbols = pivot.index[pivot.reindex(columns=timeframes, fill_value=False).all(axis=1)].tolist()
    else:
        good_symbols = all_df.loc[all_df["match"], "symbol"].unique().tolist()

    matches = all_df[all_df["symbol"].isin(good_symbols)].copy()
    matches = matches.sort_values(["score", "market_cap"], ascending=[False, False])
    return matches, all_df

st.title("📈 NIFTY 500 Bullish Momentum Scanner")
st.caption("Yahoo Finance data • NIFTY 500 universe • Market cap filter • 15 Min / 1 Hour / 1 Day")

with st.sidebar:
    st.header("Scanner Settings")
    selected_tfs = st.multiselect(
        "Timeframe filters",
        ["15 Min", "1 Hour", "1 Day"],
        default=["1 Day"],
        help="The same strategy rules are evaluated independently on every selected timeframe."
    )
    match_mode = st.radio("Multi-timeframe rule", ["ANY selected timeframe", "ALL selected timeframes"])
    min_cap_cr = st.number_input("Minimum market cap (₹ Crore)", min_value=1000, value=10000, step=1000)
    st.divider()
    st.markdown("### Strategy rules")
    st.markdown("""
    1. Close > EMA 20  
    2. EMA 20 > EMA 50  
    3. MACD Line > 0  
    4. MACD Histogram > 0  
    5. RSI 14 > 55 and < 70  
    6. Stochastic (14,3,3) > 40 and < 75  
    7. Volume > SMA(Volume,20)
    """)
    refresh = st.button("🔄 Refresh universe & data", use_container_width=True)

if refresh:
    st.cache_data.clear()

try:
    universe_raw = get_nifty500_universe()
except Exception as e:
    st.error(f"Unable to load NIFTY 500 universe: {e}")
    st.stop()

source = universe_raw["source"].iloc[0]
st.info(f"Universe source: {source}. NIFTY 500 list is refreshed automatically every 24 hours while the app is running.")

col1, col2, col3 = st.columns(3)
col1.metric("NIFTY universe", len(universe_raw))
col2.metric("Market-cap threshold", f"₹{min_cap_cr:,.0f} Cr")
col3.metric("Selected timeframes", len(selected_tfs))

if not selected_tfs:
    st.warning("Select at least one timeframe.")
    st.stop()

st.markdown("### Step 1 — Build eligible universe")
if "eligible_universe" not in st.session_state or refresh:
    with st.spinner("Checking market capitalisation from Yahoo Finance..."):
        st.session_state["eligible_universe"] = get_large_cap_universe(
            universe_raw["symbol"].tolist(), min_cap_cr * 10_000_000
        )

eligible = st.session_state["eligible_universe"]
st.success(f"Eligible stocks with market cap ≥ ₹{min_cap_cr:,.0f} Cr: {len(eligible)}")

with st.expander("View eligible universe"):
    show_u = eligible.copy()
    show_u["market_cap_cr"] = show_u["market_cap"] / 10_000_000
    st.dataframe(show_u[["symbol", "market_cap_cr"]], use_container_width=True, hide_index=True)

run = st.button("▶ Run Momentum Scan", type="primary", use_container_width=True)

if run:
    progress = st.progress(0, text="Starting scan...")
    status = st.empty()
    def update(p, txt):
        progress.progress(min(p, 1.0), text=txt)

    matches, all_results = scan(eligible, selected_tfs, match_mode, update)
    progress.empty()

    st.session_state["matches"] = matches
    st.session_state["all_results"] = all_results
    st.session_state["scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if "matches" in st.session_state:
    matches = st.session_state["matches"]
    all_results = st.session_state["all_results"]

    st.markdown(f"## Scan Results — {st.session_state['scan_time']}")
    st.caption("A result is shown when it satisfies the selected multi-timeframe rule.")

    if matches.empty:
        st.warning("No stocks matched all required conditions.")
    else:
        display = matches.copy()
        display["Market Cap (₹ Cr)"] = display["market_cap"] / 10_000_000
        display = display.rename(columns={
            "symbol": "Symbol", "timeframe": "Timeframe", "close": "Close",
            "score": "Score", "RSI14": "RSI 14", "STOCH_K": "Stochastic",
            "MACD": "MACD Line", "MACD_HIST": "MACD Histogram",
            "EMA20": "EMA 20", "EMA50": "EMA 50"
        })
        cols = ["Symbol", "Timeframe", "Score", "Close", "Market Cap (₹ Cr)",
                "EMA 20", "EMA 50", "MACD Line", "MACD Histogram",
                "RSI 14", "Stochastic", "volume", "vol_sma20", "as_of"]
        st.dataframe(display[cols], use_container_width=True, hide_index=True)

        csv = display.to_csv(index=False).encode("utf-8")
        st.download_button("⬇ Download results CSV", csv, "nifty500_momentum_results.csv", "text/csv")

    with st.expander("All analyzed results (including non-matches)"):
        if not all_results.empty:
            st.dataframe(all_results.drop(columns=["checks"], errors="ignore"), use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "Data note: Yahoo Finance intraday data availability and retention limits can vary. "
    "The app refreshes market data on reruns/cache expiry. Streamlit Community Cloud local storage is not a permanent database."
)
