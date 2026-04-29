# main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
import yfinance as yf
import time
from datetime import datetime
import math

# ---------------------------------------------------
# APP
# ---------------------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------
# SUPABASE CONFIG
# ---------------------------------------------------
SUPABASE_URL = "YOUR_URL"
SUPABASE_KEY = "YOUR_KEY"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------------
# NIFTY LIST (extend later)
# ---------------------------------------------------
NIFTY150 = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "LT", "SBIN", "ITC", "HINDUNILVR", "KOTAKBANK"
]

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------
def safe(v):
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return float(v)
    except:
        return None

def pct(a, b):
    try:
        if b == 0 or b is None:
            return None
        return (a / b) * 100
    except:
        return None

def get_latest(series):
    try:
        return float(series.iloc[0])
    except:
        return None

# ---------------------------------------------------
# ANALYZE STOCK
# ---------------------------------------------------
def analyze_stock(symbol):

    try:
        stock = yf.Ticker(symbol + ".NS")

        hist = stock.history(period="1y")
        if hist.empty:
            return None

        price = float(hist["Close"].iloc[-1])
        dma50 = float(hist["Close"].tail(50).mean())
        dma200 = float(hist["Close"].tail(200).mean())

        fin = stock.financials
        bs = stock.balance_sheet
        cf = stock.cashflow

        revenue = net_income = ebit = 0
        equity = debt = 0
        current_assets = current_liabilities = total_assets = 0
        op_cf = capex = 0

        # Income
        for idx in fin.index:
            n = str(idx).lower()
            if "revenue" in n:
                revenue = get_latest(fin.loc[idx])
            if "net income" in n:
                net_income = get_latest(fin.loc[idx])
            if "ebit" in n:
                ebit = get_latest(fin.loc[idx])

        # Balance
        for idx in bs.index:
            n = str(idx).lower()

            if "equity" in n:
                equity = get_latest(bs.loc[idx])

            if "current assets" in n:
                current_assets = get_latest(bs.loc[idx])

            if "current liabilities" in n:
                current_liabilities = get_latest(bs.loc[idx])

            if "total assets" in n:
                total_assets = get_latest(bs.loc[idx])

            if "debt" in n or "borrowings" in n:
                d = get_latest(bs.loc[idx])
                if d:
                    debt += d

        # Cashflow
        for idx in cf.index:
            n = str(idx).lower()

            if "operating cash flow" in n:
                op_cf = get_latest(cf.loc[idx])

            if "capital expenditure" in n:
                capex = abs(get_latest(cf.loc[idx]))

        # Ratios
        roe = pct(net_income, equity)
        roce = pct(ebit, (total_assets - current_liabilities))
        debt_equity = debt / equity if equity else None
        current_ratio = (
            current_assets / current_liabilities
            if current_liabilities else None
        )
        fcf = op_cf - capex if op_cf else None

        # Growth fallback (stable default)
        sales_growth = 12
        profit_growth = 12

        # ---------------- SCORING ----------------
        def wealth():
            score = 0
            if roe and roe > 15: score += 2
            if roce and roce > 18: score += 2
            if debt_equity is not None and debt_equity < 0.5: score += 2
            if sales_growth > 10: score += 1
            if profit_growth > 10: score += 1
            if fcf and fcf > 0: score += 1
            if current_ratio and current_ratio > 1.5: score += 1
            return score

        def multibagger():
            score = 0
            if sales_growth > 20: score += 2
            if profit_growth > 25: score += 2
            if roce and roce > 20: score += 2
            if debt_equity is not None and debt_equity < 0.3: score += 2
            if price > dma200: score += 1
            return score

        def balanced():
            score = 0
            if roce and roce > 18: score += 2
            if debt_equity is not None and debt_equity < 0.4: score += 2
            if sales_growth > 15: score += 2
            if profit_growth > 15: score += 2
            if current_ratio and current_ratio > 1.2: score += 1
            return score

        return {
            "stock": symbol,
            "metrics": {
                "roe": roe,
                "roce": roce,
                "debt": debt_equity,
                "fcf": fcf,
                "current_ratio": current_ratio
            },
            "wealth": wealth(),
            "multibagger": multibagger(),
            "balanced": balanced()
        }

    except:
        return None

# ---------------------------------------------------
# STORE SNAPSHOT (PERMANENT)
# ---------------------------------------------------
def store_snapshot(symbol, metrics):

    today = datetime.now().strftime("%Y-%m-%d")

    existing = supabase.table("stock_history")\
        .select("*")\
        .eq("ticker", symbol)\
        .eq("date", today)\
        .execute()

    if existing.data:
        return

    supabase.table("stock_history").insert({
        "ticker": symbol,
        "date": today,
        "roe": metrics.get("roe"),
        "roce": metrics.get("roce"),
        "debt": metrics.get("debt"),
        "fcf": metrics.get("fcf"),
        "current_ratio": metrics.get("current_ratio")
    }).execute()

# ---------------------------------------------------
# TRACK DAILY
# ---------------------------------------------------
@app.get("/track")
def track():

    for stock in NIFTY150:

        data = analyze_stock(stock)
        if not data:
            continue

        store_snapshot(stock, data["metrics"])
        time.sleep(1)

    return {"status": "Tracked successfully"}

# ---------------------------------------------------
# COMPARE
# ---------------------------------------------------
def compare_logic(prev, curr):

    score = 0

    if curr["roe"] and prev["roe"]:
        score += 1 if curr["roe"] > prev["roe"] else -1

    if curr["debt"] and prev["debt"]:
        score += 1 if curr["debt"] < prev["debt"] else -1

    if curr["fcf"] and prev["fcf"]:
        score += 1 if curr["fcf"] > prev["fcf"] else -1

    if curr["current_ratio"] and prev["current_ratio"]:
        score += 1 if curr["current_ratio"] > prev["current_ratio"] else -1

    if score >= 2:
        return "BUY 🟢"
    elif score <= -2:
        return "SELL 🔴"
    else:
        return "HOLD 🟡"

@app.get("/compare")
def compare(ticker: str):

    ticker = ticker.upper()

    res = supabase.table("stock_history")\
        .select("*")\
        .eq("ticker", ticker)\
        .order("date", desc=True)\
        .limit(2)\
        .execute()

    if len(res.data) < 2:
        return {"message": "Not enough data"}

    curr = res.data[0]
    prev = res.data[1]

    signal = compare_logic(prev, curr)

    return {
        "stock": ticker,
        "previous": prev,
        "current": curr,
        "signal": signal
    }

# ---------------------------------------------------
# SCREENER
# ---------------------------------------------------
@app.get("/screener")
def screener():

    results = {
        "wealth": [],
        "multibagger": [],
        "balanced": []
    }

    for stock in NIFTY150:

        data = analyze_stock(stock)
        if not data:
            continue

        if data["wealth"] >= 7:
            results["wealth"].append(data)

        if data["multibagger"] >= 6:
            results["multibagger"].append(data)

        if data["balanced"] >= 6:
            results["balanced"].append(data)

        time.sleep(1)

    return {
        "updated": datetime.now().strftime("%d-%b %H:%M"),
        "results": results
    }