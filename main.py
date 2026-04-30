from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import time
import random

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- CACHE ----------------
cache = {}

# ---------------- RATIO META ----------------
RATIO_INFO = {
    "ROE": {
        "def": "For every ₹100 shareholders invest, company earns this much profit.",
        "ideal": "> 15%",
        "better": "higher",
        "good": lambda x: x > 15,
        "percent": True
    },
    "ROCE": {
        "def": "How efficiently company uses total capital (equity + debt).",
        "ideal": "> 18%",
        "better": "higher",
        "good": lambda x: x > 18,
        "percent": True
    },
    "Debt": {
        "def": "How much company depends on borrowed money.",
        "ideal": "< 0.5",
        "better": "lower",
        "good": lambda x: x < 0.5,
        "percent": False
    },
    "PE": {
        "def": "How expensive the stock is compared to its earnings.",
        "ideal": "< 25",
        "better": "lower",
        "good": lambda x: x < 25,
        "percent": False
    },
    "PB": {
        "def": "Price vs actual book value of the company.",
        "ideal": "< 3",
        "better": "lower",
        "good": lambda x: x < 3,
        "percent": False
    },
    "Dividend": {
        "def": "Cash return you get for holding the stock.",
        "ideal": "> 1%",
        "better": "higher",
        "good": lambda x: x > 1,
        "percent": True
    },
}

# ---------------- SAFE HELPERS ----------------
def safe_div(a, b):
    if a is None or b in [None, 0]:
        return None
    try:
        return a / b
    except:
        return None

def safe_sub(a, b):
    if a is None or b is None:
        return None
    try:
        return a - b
    except:
        return None

def fetch_hist(stock):
    for _ in range(3):
        try:
            d = stock.history(period="1y")
            if d is not None and not d.empty:
                return d
        except:
            pass
        time.sleep(2 + random.random())
    return None

def get(df, keys):
    try:
        if df is None or df.empty:
            return None
        for idx in df.index:
            name = str(idx).lower()
            if any(k in name for k in keys):
                val = df.loc[idx].iloc[0]
                return float(val) if val is not None else None
    except:
        pass
    return None

# ---------------- ANALYZE ----------------
@app.get("/analyze")
def analyze(ticker: str):
    ticker = (ticker or "").upper()

    if ticker in cache:
        return cache[ticker]

    try:
        stock = yf.Ticker(ticker + ".NS")

        hist = fetch_hist(stock)
        if hist is None:
            return {"error": "Data busy. Try again."}

        price = float(hist["Close"].iloc[-1])
        dma200 = float(hist["Close"].tail(200).mean())

        fin = stock.financials
        bs = stock.balance_sheet

        net_income = get(fin, ["net income"])
        ebit = get(fin, ["ebit"])
        equity = get(bs, ["equity"])
        debt = get(bs, ["debt", "borrowings"])
        total_assets = get(bs, ["total assets"])
        current_liabilities = get(bs, ["current liabilities"])

        roe = safe_div(net_income, equity)
        roce = safe_div(ebit, safe_sub(total_assets, current_liabilities))
        debt_eq = safe_div(debt, equity)

        info = stock.info or {}
        pe = info.get("trailingPE")
        pb = info.get("priceToBook")
        dividend = info.get("dividendYield")
        if dividend is not None:
            dividend *= 100

        raw = {
            "ROE": roe * 100 if roe is not None else None,
            "ROCE": roce * 100 if roce is not None else None,
            "Debt": debt_eq,
            "PE": pe,
            "PB": pb,
            "Dividend": dividend
        }

        ratios = []
        score = 0
        total = 0

        for k, v in raw.items():
            meta = RATIO_INFO.get(k)
            if v is None or meta is None:
                continue

            total += 1
            good = meta["good"](v)
            if good:
                score += 1

            display_val = f"{round(v, 2)}%" if meta["percent"] else round(v, 2)

            ratios.append({
                "name": k,
                "value": display_val,
                "ideal": meta["ideal"],
                "definition": meta["def"],
                "interpretation": f"{meta['better']} is better",
                "status": "GOOD" if good else "BAD"
            })

        trend = price > dma200
        total += 1
        if trend:
            score += 1

        final_score = round((score / total) * 10, 1) if total else 0.0

        if final_score >= 8:
            verdict = "STRONG BUY 🟢"
        elif final_score >= 6:
            verdict = "BUY 🟢"
        elif final_score >= 4:
            verdict = "HOLD 🟡"
        else:
            verdict = "AVOID 🔴"

        reasons = [
            f"{r['name']} is {'strong' if r['status']=='GOOD' else 'weak'}"
            for r in ratios
        ]
        reasons.append("Uptrend in price" if trend else "Downtrend in price")

        response = {
            "stock": ticker,
            "price": round(price, 2),
            "score": final_score,
            "verdict": verdict,
            "trend": "UPTREND" if trend else "DOWNTREND",
            "ratios": ratios,
            "reasons": reasons
        }

        cache[ticker] = response
        return response

    except Exception as e:
        return {"error": str(e)}

# ---------------- SCREENER (3 TYPES) ----------------

STOCKS = [
"BAJFINANCE","RELIANCE","HDFCBANK","ICICIBANK","BHARTIARTL","ADANIENT",
"AXISBANK","COALINDIA","INDIGO","ONGC","LT","INFY","M&M","SBIN",
"TCS","MARUTI","TATASTEEL","SUNPHARMA","ITC","HINDALCO","ULTRACEMCO",
"EICHERMOT","HCLTECH","POWERGRID","KOTAKBANK","WIPRO","NTPC",
"BAJAJ-AUTO","TECHM","HINDUNILVR","DRREDDY","CIPLA","TITAN"
]

def basic_ratios_for_screen(ticker):
    try:
        stock = yf.Ticker(ticker + ".NS")
        hist = fetch_hist(stock)
        if hist is None:
            return None

        price = float(hist["Close"].iloc[-1])
        dma50 = float(hist["Close"].tail(50).mean())
        dma200 = float(hist["Close"].tail(200).mean())

        fin = stock.financials
        bs = stock.balance_sheet

        net_income = get(fin, ["net income"])
        ebit = get(fin, ["ebit"])
        equity = get(bs, ["equity"])
        debt = get(bs, ["debt", "borrowings"])
        total_assets = get(bs, ["total assets"])
        current_assets = get(bs, ["current assets"])
        current_liabilities = get(bs, ["current liabilities"])

        roe = safe_div(net_income, equity)
        roce = safe_div(ebit, safe_sub(total_assets, current_liabilities))
        debt_eq = safe_div(debt, equity)
        current_ratio = safe_div(current_assets, current_liabilities)

        info = stock.info or {}
        pe = info.get("trailingPE")
        market_cap = info.get("marketCap")

        return {
            "price": price,
            "dma50": dma50,
            "dma200": dma200,
            "roe": roe * 100 if roe else None,
            "roce": roce * 100 if roce else None,
            "debt": debt_eq,
            "current_ratio": current_ratio,
            "pe": pe,
            "market_cap": market_cap
        }
    except:
        return None

@app.get("/screener")
def screener(type: str):
    results = []

    for s in STOCKS:
        d = basic_ratios_for_screen(s)
        if d is None:
            continue

        try:
            if type == "allrounder":
                if (
                    d["roe"] and d["roe"] > 15 and
                    d["roce"] and d["roce"] > 18 and
                    d["debt"] is not None and d["debt"] < 0.5 and
                    d["current_ratio"] and d["current_ratio"] > 1.5 and
                    d["pe"] and d["pe"] < 25 and
                    d["price"] > d["dma200"] and
                    d["price"] > d["dma50"]
                ):
                    results.append({"stock": s, "tag": "ALL-ROUNDER", "signal": "BUY 🟢"})

            elif type == "multibagger":
                if (
                    d["roe"] and d["roe"] > 20 and
                    d["roce"] and d["roce"] > 20 and
                    d["debt"] is not None and d["debt"] < 0.3 and
                    d["pe"] and d["pe"] < 30 and
                    d["market_cap"] and d["market_cap"] > 500e7
                ):
                    results.append({"stock": s, "tag": "MULTIBAGGER", "signal": "BUY 🚀"})

            elif type == "bluechip":
                if (
                    d["market_cap"] and d["market_cap"] > 20000e7 and
                    d["roe"] and d["roe"] > 15 and
                    d["roce"] and d["roce"] > 18 and
                    d["debt"] is not None and d["debt"] < 0.5
                ):
                    results.append({"stock": s, "tag": "BLUECHIP", "signal": "SAFE 🛡️"})
        except:
            continue

    return {"stocks": results}
