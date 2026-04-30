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

# -------- DEFINITIONS + IDEAL RANGES --------

RATIO_INFO = {
    "ROE": {"def": "Return on Equity", "ideal": "> 15%", "good": lambda x: x > 15},
    "ROCE": {"def": "Return on Capital", "ideal": "> 18%", "good": lambda x: x > 18},
    "Debt": {"def": "Debt to Equity", "ideal": "< 0.5", "good": lambda x: x < 0.5},
    "CurrentRatio": {"def": "Liquidity", "ideal": "> 1.5", "good": lambda x: x > 1.5},
    "PE": {"def": "Price to Earnings", "ideal": "< 25", "good": lambda x: x < 25},
    "PB": {"def": "Price to Book", "ideal": "< 3", "good": lambda x: x < 3},
    "Dividend": {"def": "Dividend Yield", "ideal": "> 1%", "good": lambda x: x > 1},
}

# -------- SAFE FUNCTIONS --------

def safe_div(a, b):
    if a is None or b in [None, 0]:
        return None
    return a / b

def safe_sub(a, b):
    if a is None or b is None:
        return None
    return a - b

def fetch(stock):
    for _ in range(3):
        try:
            d = stock.history(period="1y")
            if not d.empty:
                return d
        except:
            pass
        time.sleep(2)
    return None

def get(df, keys):
    try:
        for idx in df.index:
            name = str(idx).lower()
            if any(k in name for k in keys):
                return float(df.loc[idx].iloc[0])
    except:
        pass
    return None

# -------- MAIN API --------

@app.get("/analyze")
def analyze(ticker: str):

    ticker = ticker.upper()

    if ticker in cache:
        return cache[ticker]

    try:
        stock = yf.Ticker(ticker + ".NS")

        hist = fetch(stock)
        if hist is None:
            return {"error": "Data busy"}

        price = float(hist["Close"].iloc[-1])
        dma200 = float(hist["Close"].tail(200).mean())

        fin = stock.financials
        bs = stock.balance_sheet

        net_income = get(fin, ["net income"])
        ebit = get(fin, ["ebit"])

        equity = get(bs, ["equity"])
        debt = get(bs, ["debt"])
        total_assets = get(bs, ["total assets"])
        current_liabilities = get(bs, ["current liabilities"])

        # -------- RATIOS --------

        roe = safe_div(net_income, equity)
        roce = safe_div(ebit, safe_sub(total_assets, current_liabilities))
        debt_eq = safe_div(debt, equity)

        pe = stock.info.get("trailingPE")
        pb = stock.info.get("priceToBook")
        dividend = stock.info.get("dividendYield")

        if dividend:
            dividend *= 100

        # -------- FORMAT --------

        def pct(x):
            return round(x * 100, 2) if x else None

        def num(x):
            return round(x, 2) if x else None

        ratios = {
            "ROE": pct(roe),
            "ROCE": pct(roce),
            "Debt": num(debt_eq),
            "PE": num(pe),
            "PB": num(pb),
            "Dividend": num(dividend),
        }

        # -------- SCORING /10 --------

        score = 0
        max_score = 0
        details = []

        for k, v in ratios.items():
            info = RATIO_INFO.get(k)

            if v is None or info is None:
                continue

            max_score += 1
            good = info["good"](v)

            if good:
                score += 1

            details.append({
                "name": k,
                "value": v,
                "ideal": info["ideal"],
                "definition": info["def"],
                "status": "GOOD" if good else "BAD"
            })

        # -------- TECH --------
        trend = price > dma200

        if trend:
            score += 1
        max_score += 1

        # -------- FINAL SCORE --------

        final_score = round((score / max_score) * 10, 1) if max_score else 0

        # -------- VERDICT --------

        if final_score >= 8:
            verdict = "STRONG BUY 🟢"
        elif final_score >= 6:
            verdict = "BUY 🟢"
        elif final_score >= 4:
            verdict = "HOLD 🟡"
        else:
            verdict = "AVOID 🔴"

        response = {
            "stock": ticker,
            "price": price,
            "score": final_score,
            "verdict": verdict,
            "ratios": details,
            "trend": "UPTREND" if trend else "DOWNTREND"
        }

        cache[ticker] = response
        return response

    except Exception as e:
        return {"error": str(e)}