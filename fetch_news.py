"""Pulls market headlines (Google News RSS) + commodity/FX/VIX snapshot -> news.json"""
import json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

TOPICS = {
    "Energy": "crude oil OR Brent OR OPEC",
    "Metals": "gold price OR silver price",
    "Geopolitics": "war OR ceasefire OR sanctions OR Middle East",
    "US & Trump": "Trump tariffs OR Trump speech OR Federal Reserve",
    "India Economy": "RBI OR India GDP OR India inflation OR India economy",
    "Markets": "Sensex OR Nifty OR FPI OR rupee",
}
PULSE = [("Brent", "BZ=F"), ("WTI crude", "CL=F"), ("Gold", "GC=F"), ("Silver", "SI=F"),
         ("USD/INR", "INR=X"), ("India VIX", "^INDIAVIX"), ("US 10Y", "^TNX"), ("Dollar index", "DX-Y.NYB")]
HOT = re.compile(r"crash|surge|plunge|soar|record|tariff|sanction|war|attack|ceasefire|rate cut|rate hike|RBI|Fed|OPEC|default|emergency|spike", re.I)

def parse(xml_text, topic, now):
    out = []
    for it in ET.fromstring(xml_text).iter("item"):
        title = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        try:
            ts = int(parsedate_to_datetime(it.findtext("pubDate")).timestamp())
        except Exception:
            continue
        if now - ts > 36 * 3600 or not title:
            continue
        out.append({"t": title, "u": it.findtext("link") or "", "s": src, "topic": topic,
                    "ts": ts, "hot": bool(HOT.search(title))})
    return out

def news():
    now, seen, items = int(time.time()), set(), []
    for topic, q in TOPICS.items():
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:1d")
               + "&hl=en-IN&gl=IN&ceid=IN:en")
        try:
            xml_text = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()
            got = sorted(parse(xml_text, topic, now), key=lambda x: -x["ts"])[:6]
        except Exception as e:
            print("feed failed", topic, e); continue
        for x in got:
            k = x["t"].lower()[:60]
            if k not in seen:
                seen.add(k); items.append(x)
    return sorted(items, key=lambda x: -x["ts"])[:40]

def pulse():
    import yfinance as yf
    out = []
    for name, t in PULSE:
        try:
            c = yf.Ticker(t).history(period="5d")["Close"].dropna()
            out.append({"n": name, "p": round(float(c.iloc[-1]), 2),
                        "c": round(float((c.iloc[-1] / c.iloc[-2] - 1) * 100), 2)})
        except Exception as e:
            print("price failed", name, e)
    return out

if __name__ == "__main__":
    items = news()
    if not items:
        sys.exit("No headlines fetched.")
    json.dump({"updated": int(time.time()), "pulse": pulse(), "items": items}, open("news.json", "w"))
    print(len(items), "headlines")
