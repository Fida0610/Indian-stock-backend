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

cache = {}
cache_time = {}
CACHE_TTL = 300

# ---------- SAFE ----------
def safe_div(a, b):
    if a is None or b in [None, 0]:
        return None
    return a / b

def fetch(stock):
    for _ in range(5):
        try:
            data = stock.history(period="1y")
            if not data.empty:
                return data
        except:
            pass
        time.sleep(3 + random.random())
    return None

def get(df, keys):
    try:
        if df is None or df.empty:
            return None
        for idx in df.index:
            name = str(idx).lower()
            if any(k in name for k in keys):
                return float(df.loc[idx].iloc[0])
    except:
        pass
    return None

# ---------- WATERFALL ----------
def compute_ratios(stock):

    hist = fetch(stock)
    if hist is None:
        return None

    price = float(hist["Close"].iloc[-1])
    dma50 = float(hist["Close"].tail(50).mean())
    dma200 = float(hist["Close"].tail(200).mean())

    fin = stock.financials
    bs = stock.balance_sheet
    info = stock.info or {}

    # waterfall extraction
    net_income = get(fin, ["net income"])
    ebit = get(fin, ["ebit"])
    equity = get(bs, ["equity"])
    debt = get(bs, ["debt", "borrowings"])
    total_assets = get(bs, ["total assets"])
    current_assets = get(bs, ["current assets"])
    current_liabilities = get(bs, ["current liabilities"])

    roe = safe_div(net_income, equity)
    roce = safe_div(ebit, (total_assets - current_liabilities) if total_assets and current_liabilities else None)
    debt_eq = safe_div(debt, equity)
    current_ratio = safe_div(current_assets, current_liabilities)

    pe = info.get("trailingPE")
    pb = info.get("priceToBook")
    dividend = info.get("dividendYield")
    if dividend:
        dividend *= 100

    return {
        "price": price,
        "dma50": dma50,
        "dma200": dma200,
        "ROE": roe * 100 if roe else None,
        "ROCE": roce * 100 if roce else None,
        "Debt": debt_eq,
        "PE": pe,
        "PB": pb,
        "Dividend": dividend,
        "CurrentRatio": current_ratio
    }

# ---------- ANALYZE ----------
@app.get("/analyze")
def analyze(ticker: str):

    ticker = ticker.upper()
    now = time.time()

    if ticker in cache and now - cache_time.get(ticker, 0) < CACHE_TTL:
        return cache[ticker]

    stock = yf.Ticker(ticker + ".NS")
    data = compute_ratios(stock)

    if data is None:
        return {"error": "Server busy. Try again later."}

    ratios = []
    score = 0
    total = 0

    def check(name, val, cond, ideal, better, definition, percent=False):
        nonlocal score, total

        if val is None:
            return

        total += 1
        good = cond(val)
        if good:
            score += 1

        display = f"{round(val,2)}%" if percent else round(val,2)

        ratios.append({
            "name": name,
            "value": display,
            "ideal": ideal,
            "definition": definition,
            "interpretation": f"{better} is better",
            "status": "GOOD" if good else "BAD"
        })

    # apply waterfall checks
    check("ROE", data["ROE"], lambda x: x > 15, ">15%", "higher",
          "Profit generated per ₹100 shareholder money", True)

    check("ROCE", data["ROCE"], lambda x: x > 18, ">18%", "higher",
          "Efficiency of total capital", True)

    check("Debt", data["Debt"], lambda x: x < 0.5, "<0.5", "lower",
          "Debt burden of company")

    check("PE", data["PE"], lambda x: x < 25, "<25", "lower",
          "Valuation vs earnings")

    check("PB", data["PB"], lambda x: x < 3, "<3", "lower",
          "Valuation vs assets")

    check("Dividend", data["Dividend"], lambda x: x > 1, ">1%", "higher",
          "Cash return to shareholders", True)

    # trend
    trend = data["price"] > data["dma200"]
    total += 1
    if trend:
        score += 1

    final_score = round((score / total) * 10, 1) if total else 0

    verdict = (
        "STRONG BUY 🟢" if final_score >= 8 else
        "BUY 🟢" if final_score >= 6 else
        "HOLD 🟡" if final_score >= 4 else
        "AVOID 🔴"
    )

    response = {
        "stock": ticker,
        "price": round(data["price"], 2),
        "score": final_score,
        "verdict": verdict,
        "trend": "UPTREND" if trend else "DOWNTREND",
        "ratios": ratios,
        "reasons": [f"{r['name']} is {r['status']}" for r in ratios]
    }

    cache[ticker] = response
    cache_time[ticker] = now

    return response