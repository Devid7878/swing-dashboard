"""Market news (publisher RSS + Google News) with India-impact analysis, plus price snapshot -> news.json"""
import html, json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

# (url, default topic) - publisher feeds carry a short teaser + image
FEEDS = [
    ("https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "Markets"),
    ("https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms", "India Economy"),
    ("https://www.moneycontrol.com/rss/marketreports.xml", "Markets"),
    ("https://www.moneycontrol.com/rss/economy.xml", "India Economy"),
    ("https://www.livemint.com/rss/markets", "Markets"),
    ("https://www.livemint.com/rss/economy", "India Economy"),
    ("https://www.business-standard.com/rss/markets-106.rss", "Markets"),
    ("https://www.thehindubusinessline.com/markets/feeder/default.rss", "Markets"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml", "Markets"),
    ("https://feeds.bbci.co.uk/news/world/rss.xml", "Geopolitics"),
]
TOPICS = {  # Google News searches: headlines only, fills gaps (Trump, war, crude, metals)
    "Energy": "crude oil OR Brent OR OPEC", "Metals": "gold price OR silver price",
    "Geopolitics": "war OR ceasefire OR sanctions OR Middle East",
    "US & Trump": "Trump tariffs OR Trump speech OR Federal Reserve",
    "India Economy": "RBI OR India GDP OR India inflation OR India economy",
    "Markets": "Sensex OR Nifty OR FPI OR rupee"}
TOPIC_RULES = [("Energy", r"crude|brent|opec|oil price|natural gas|petrol|diesel"),
    ("Metals", r"\bgold\b|\bsilver\b|copper|aluminium|steel"),
    ("US & Trump", r"trump|fed\b|federal reserve|powell|white house|us tariff"),
    ("Geopolitics", r"\bwar\b|missile|ceasefire|iran|israel|ukraine|russia|hormuz|red sea|sanction|taiwan"),
    ("India Economy", r"\brbi\b|gdp|inflation|cpi|\bgst\b|budget|repo rate|fiscal|pmi")]
# (regex, weight, why, sectors)
IMPACT = [
 (r"\b(crude|brent|wti|opec|oil prices?)\b", 3, "Crude oil: India imports most of its oil, so moves hit the rupee, inflation, OMCs, airlines and paints", ["OMCs", "Aviation", "Paints"]),
 (r"\b(rbi|repo rate|monetary policy|mpc|rate cut|rate hike|crr)\b", 3, "RBI / interest rates: drives banks, NBFCs, housing and rate-sensitive stocks", ["Banks", "NBFCs", "Realty"]),
 (r"\b(fiis?|fpis?|foreign (portfolio )?investors?|dii)\b", 3, "Investor flows: foreign and domestic buying/selling directly moves Nifty and the rupee", ["Broad market"]),
 (r"\b(tariffs?|trade deal|trade war|export curbs?|sanctions?)\b", 3, "Tariffs / trade: hits exporters such as IT, pharma, textiles and auto parts", ["Exporters", "Pharma", "Textiles"]),
 (r"\b(fed|federal reserve|powell|treasury yields?|us yields?|dollar index|dxy)\b", 2, "US rates / dollar: tighter US conditions pull foreign money out of Indian equities", ["IT", "Banks"]),
 (r"\b(war|missile|strikes?|iran|israel|hormuz|red sea|ceasefire|ukraine|russia|taiwan)\b", 2, "Geopolitics: risk-off for equities and a spike risk for crude", ["Defence", "OMCs"]),
 (r"\b(rupee|usd/inr|dollar[- ]rupee)\b", 2, "Rupee: affects importers, IT earnings and foreign investor returns", ["IT", "Importers"]),
 (r"\b(inflation|cpi|wpi|gdp|pmi|iip|gst|budget|fiscal deficit|current account)\b", 2, "India macro data: shapes rate expectations and the earnings outlook", ["Broad market"]),
 (r"\b(sensex|nifty|bank nifty)\b", 1, "Direct index move", ["Broad market"]),
 (r"\b(crash|plunge|tumble|surge|soar|record high|slump|rally)\b", 1, "Sharp market move", []),
 (r"\b(gold|silver)\b", 1, "Gold / silver: import bill, jewellery stocks and safe-haven flows", ["Jewellery"]),
 (r"\b(china|stimulus)\b", 1, "China: moves metals and global risk appetite", ["Metals"]),
 (r"\b(india|indian|sebi|nse|bse)\b", 1, "India-specific news", []),
]

def analyze(text):
    hits = [(w, why, sec) for rx, w, why, sec in IMPACT if re.search(rx, text, re.I)]
    score = sum(h[0] for h in hits)
    imp = 3 if score >= 5 else 2 if score >= 3 else 1 if score >= 1 else 0
    top = sorted((h for h in hits if h[0] >= 2), key=lambda h: -h[0])[:2] or hits[:1]
    sec = []
    for h in sorted(hits, key=lambda h: -h[0]):
        for s in h[2]:
            if s not in sec:
                sec.append(s)
    return imp, " · ".join(h[1] for h in top), sec[:4]

def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > 300:
        cut = s[:300]
        k = cut.rfind(". ")
        s = cut[: k + 1] if k > 120 else cut[: cut.rfind(" ")] + "…"
    return s

def image(it, raw_desc):
    for ch in it.iter():
        tag = ch.tag.split("}")[-1]
        if tag in ("content", "thumbnail", "enclosure") and ch.get("url"):
            if tag == "enclosure" and not (ch.get("type") or "").startswith("image"):
                continue
            if tag == "content" and ch.get("medium") not in (None, "image") and "image" not in (ch.get("type") or "image"):
                continue
            return ch.get("url")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', raw_desc or "")
    return m.group(1) if m else ""

def topic_for(text, default):
    for t, rx in TOPIC_RULES:
        if re.search(rx, text, re.I):
            return t
    return default

def parse(xml_text, default, now, google=False):
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
        if not title or now - ts > 36 * 3600:
            continue
        raw = it.findtext("description") or ""
        summ = "" if google else clean(raw)
        topic = default if google else topic_for(title + " " + summ, default)
        imp, why, sec = analyze(title + " " + summ)
        out.append({"t": title, "u": (it.findtext("link") or "").strip(), "s": src, "topic": topic,
                    "ts": ts, "sum": summ, "img": "" if google else image(it, raw),
                    "imp": imp, "why": why, "sec": sec})
    return out

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=20).read()

def news():
    now, seen, items = int(time.time()), set(), []
    def add(batch):
        for x in batch:
            k = re.sub(r"\W+", "", x["t"].lower())[:60]
            if k not in seen:
                seen.add(k); items.append(x)
    for url, topic in FEEDS:
        try:
            host = urllib.parse.urlparse(url).netloc.replace("www.", "")
            got = parse(get(url), topic, now)
            for x in got:
                x["s"] = x["s"] or host
            add(sorted(got, key=lambda x: -x["ts"])[:10])
        except Exception as e:
            print("feed failed", url, e)
    for topic, q in TOPICS.items():
        try:
            u = "https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:1d") + "&hl=en-IN&gl=IN&ceid=IN:en"
            add(sorted(parse(get(u), topic, now, google=True), key=lambda x: -x["ts"])[:5])
        except Exception as e:
            print("google failed", topic, e)
    return sorted(items, key=lambda x: -x["ts"])[:60]

PULSE = [("Brent", "BZ=F"), ("WTI crude", "CL=F"), ("Gold", "GC=F"), ("Silver", "SI=F"),
         ("USD/INR", "INR=X"), ("India VIX", "^INDIAVIX"), ("US 10Y", "^TNX"), ("Dollar index", "DX-Y.NYB")]

def pulse():
    import yfinance as yf
    out = []
    for name, t in PULSE:
        try:
            c = yf.Ticker(t).history(period="5d")["Close"].dropna()
            out.append({"n": name, "p": round(float(c.iloc[-1]), 2), "c": round(float((c.iloc[-1] / c.iloc[-2] - 1) * 100), 2)})
        except Exception as e:
            print("price failed", name, e)
    return out

if __name__ == "__main__":
    items = news()
    if not items:
        sys.exit("No headlines fetched.")
    json.dump({"updated": int(time.time()), "pulse": pulse(), "items": items}, open("news.json", "w"))
    print(len(items), "headlines,", sum(1 for i in items if i["imp"] >= 2), "important")
