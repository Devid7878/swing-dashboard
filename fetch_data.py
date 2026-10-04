"""Downloads Nifty Smallcap 250 daily closes, computes EMAs, writes data.json."""
import json, os, sys
import pandas as pd
import yfinance as yf

TICKER = os.environ.get("TICKER", "NIFTYSMLCAP250.NS")

def build(close: pd.Series) -> dict:
    close = close.dropna()
    if len(close) < 200:
        sys.exit(f"Only {len(close)} rows for {TICKER}; need 200+. Check the ticker.")
    ema = lambda n: round(float(close.ewm(span=n, adjust=False).mean().iloc[-1]), 2)
    return {"date": close.index[-1].strftime("%d %b %Y"),
            "close": round(float(close.iloc[-1]), 2),
            "ema20": ema(20), "ema50": ema(50), "ema200": ema(200)}

if __name__ == "__main__":
    df = yf.download(TICKER, period="2y", interval="1d", auto_adjust=False, progress=False)
    if df.empty:
        sys.exit(f"No data returned for {TICKER}.")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    out = build(close)
    json.dump(out, open("data.json", "w"))
    print(out)
