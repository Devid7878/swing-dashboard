"""Daily job: index EMAs + breadth for the stocks listed in universe.csv -> data.json"""
import json, os, sys
import pandas as pd
import yfinance as yf

TICKER = os.environ.get("TICKER", "NIFTYSMLCAP250.NS")

def dl(tickers):
    return yf.download(tickers, period="2y", interval="1d", auto_adjust=False,
                       progress=False, threads=True)["Close"]

def index_part(close):
    close = close.dropna()
    if len(close) < 200:
        sys.exit(f"Only {len(close)} rows for {TICKER}; need 200+. Check the ticker.")
    ema = lambda n: round(float(close.ewm(span=n, adjust=False).mean().iloc[-1]), 2)
    return {"date": close.index[-1].strftime("%d %b %Y"), "close": round(float(close.iloc[-1]), 2),
            "ema20": ema(20), "ema50": ema(50), "ema200": ema(200)}

def breadth(c: pd.DataFrame, total: int) -> dict:
    c = c.dropna(axis=1, thresh=210)            # need ~1yr of history
    c = c.loc[:, c.iloc[-1].notna() & c.iloc[-2].notna()]  # traded on last 2 days
    last, prev = c.iloc[-1], c.iloc[-2]
    pct = lambda m: round(float((last > m.iloc[-1]).mean() * 100), 1)
    return {"adv": int((last > prev).sum()), "dec": int((last < prev).sum()),
            "b20": pct(c.ewm(span=20, adjust=False).mean()),
            "b50": pct(c.rolling(50).mean()), "b200": pct(c.rolling(200).mean()),
            "hi": int((last >= c.iloc[-253:-1].max()).sum()),
            "lo": int((last <= c.iloc[-253:-1].min()).sum()),
            "n": int(c.shape[1]), "skipped": total - int(c.shape[1])}

if __name__ == "__main__":
    idx = dl(TICKER)
    if idx.empty:
        sys.exit(f"No data returned for {TICKER}.")
    out = index_part(idx.iloc[:, 0] if isinstance(idx, pd.DataFrame) else idx)
    if os.path.exists("universe.csv"):
        try:
            syms = pd.read_csv("universe.csv")["Symbol"].dropna().astype(str).str.strip()
            tick = [s + ".NS" for s in syms]
            out["breadth"] = breadth(dl(tick), len(tick))
        except Exception as e:                  # index part must still be saved
            print("Breadth failed:", e)
    else:
        print("universe.csv not found: skipping breadth")
    json.dump(out, open("data.json", "w"))
    print(out)
